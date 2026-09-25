"""Durable observation around native tau2 execution; no policy guard or model judge.

The native Orchestrator.run implementation is inherited unchanged. All records
under internal/ and outcome_supplements/ are withheld from initial policy review.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

from adapter.native import CodexLLMAgent, CodexUserSimulator, ProposalError
from tau2.data_model.tasks import RewardType
from tau2.evaluator.evaluator import evaluate_simulation, EvaluationType
from tau2.orchestrator.orchestrator import Orchestrator


def plain(value):
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return value


def canonical(value):
    return json.dumps(plain(value), ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def dump(path, value):
    """Atomic, fsynced checkpoints; a killed runner leaves the previous complete file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('wb') as handle:
        handle.write(json.dumps(plain(value), ensure_ascii=False, indent=2, allow_nan=False).encode() + b'\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class PilotLimitError(RuntimeError):
    pass


def failure_kind(exc):
    # strict_json serves both the CLI event stream and the model's final JSON.
    # Identify the validation boundary before interpreting shared parser errors.
    trace = exc.__traceback__
    while trace is not None:
        frame = trace.tb_frame
        if frame.f_globals.get('__name__') == 'adapter.cli' and frame.f_code.co_name == 'validate_events':
            return 'infrastructure_failure'
        trace = trace.tb_next
    if isinstance(exc, ProposalError):
        return 'malformed_output'
    if isinstance(exc, PilotLimitError) or 'generation budget exhausted' in str(exc):
        return 'budget_exhausted'
    # Transport exposes validation errors with these explicit prefixes. Unknown
    # failures conservatively stop the pilot as infrastructure failures.
    text = str(exc).lower()
    malformed = ('malformed json', 'proposal schema', 'exactly one of',
                 'unknown native tool', 'tool arguments', 'duplicate call id',
                 'duplicate json key', 'nonfinite json number', 'arguments must be an object')
    if any(token in text for token in malformed):
        return 'malformed_output'
    return 'infrastructure_failure'


class EpisodeJournal:
    def __init__(self, output_root, episode_id, *, policy, deadline):
        self.root = Path(output_root)
        self.episode_id = episode_id
        self.directory = self.root / 'internal' / 'episodes' / episode_id
        self.directory.mkdir(parents=True, exist_ok=False)
        self.policy = policy
        self.deadline = deadline
        self.phase = 'setup'
        self.pending = None
        self.generations = []
        self.packet_by_call = {}
        self.packet_index = []
        self.execution_count = 0
        self.actor_execution_count = 0
        self.nonactor_execution_count = 0
        self.tool_error_count = 0
        self.setup_execution_count = 0
        self.sequence = 0

    def check_deadline(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise PilotLimitError('pilot wall-clock budget exhausted')
        return remaining

    def event(self, kind, **fields):
        self.sequence += 1
        row = {'sequence': self.sequence, 'utc': datetime.now(timezone.utc).isoformat(),
               'phase': self.phase, 'kind': kind, **plain(fields)}
        with (self.directory / 'events.jsonl').open('ab') as handle:
            handle.write(canonical(row) + b'\n')
            handle.flush()
            os.fsync(handle.fileno())

    def snapshot(self, environment):
        state = {name: plain(toolkit.db) if toolkit is not None else None
                 for name, toolkit in [('agent', environment.tools), ('user', environment.user_tools)]}
        sha = digest(state)
        path = self.root / 'internal' / 'state_snapshots' / (sha + '.json')
        if not path.exists():
            dump(path, state)
        return sha

    def checkpoint(self, orchestrator, *, status):
        dump(self.directory / 'partial_trajectory.json', {
            'status': status, 'step_count': orchestrator.step_count,
            'num_errors': orchestrator.num_errors, 'done': orchestrator.done,
            'termination_reason': plain(orchestrator.termination_reason),
            'from_role': plain(orchestrator.from_role), 'to_role': plain(orchestrator.to_role),
            'current_message': plain(orchestrator.message),
            'trajectory': plain(orchestrator.trajectory),
            'database_sha256': self.snapshot(orchestrator.environment),
            'funnel': self.funnel(),
        })

    def funnel(self):
        actor = [r for r in self.generations if r['role'] == 'actor']
        return {
            'generation_requests': len(self.generations), 'actor_generation_requests': len(actor),
            'user_generation_requests': len(self.generations) - len(actor),
            'interface_valid_generations': sum(r['status'] == 'interface_valid' for r in self.generations),
            'actor_tool_proposal_groups': sum(r.get('candidate_count', 0) > 0 for r in actor),
            'actor_tool_proposals': sum(r.get('candidate_count', 0) for r in actor),
            'actor_text_only': sum(r['status'] == 'interface_valid' and r.get('candidate_count') == 0 for r in actor),
            'malformed_generations': sum(r['status'] == 'malformed_output' for r in self.generations),
            'infrastructure_failures': sum(r['status'] == 'infrastructure_failure' for r in self.generations),
            'budget_failures': sum(r['status'] == 'budget_exhausted' for r in self.generations),
            'unfinished_generations': sum(r['status'] in ('started', 'returned') for r in self.generations),
            'runtime_tool_executions': self.execution_count, 'runtime_tool_errors': self.tool_error_count,
            'runtime_actor_proposal_executions': self.actor_execution_count,
            'runtime_other_origin_executions': self.nonactor_execution_count,
            'setup_tool_executions': self.setup_execution_count,
            'policy_guard_blocks': 0, 'authorization_labels_established': 0,
        }

    def start_generation(self, role, payload):
        if self.pending is not None:
            raise RuntimeError('unresolved prior generation')
        row = {'generation_id': uuid.uuid4().hex, 'role': role, 'status': 'started',
               'payload': deepcopy(payload), 'packet_ids': [], 'proposal_group_id': uuid.uuid4().hex}
        if role == 'actor':
            row['packet_ids'] = [uuid.uuid4().hex]
        self.generations.append(row)
        self.pending = row
        self.event('generation_requested', generation_id=row['generation_id'], role=role)
        self.save_generations()
        if role == 'actor':
            self.write_packets(row)

    def save_generations(self):
        dump(self.directory / 'generations.json', self.generations)
        dump(self.directory / 'packet_index.json', self.packet_index)

    def write_packets(self, row):
        calls = row.get('proposal', {}).get('tool_calls', []) if row['status'] == 'interface_valid' else []
        candidates = calls or [None]
        while len(row['packet_ids']) < len(candidates):
            row['packet_ids'].append(uuid.uuid4().hex)
        for index, candidate in enumerate(candidates):
            packet_id = row['packet_ids'][index]
            packet = {
                'packet_version': 1, 'packet_id': packet_id,
                'proposal_group_id': row['proposal_group_id'], 'group_index': index,
                'group_size': len(candidates), 'policy_text': self.policy,
                'policy_sha256': hashlib.sha256(self.policy.encode()).hexdigest(),
                'tool_schemas': deepcopy(row['payload']['tools']),
                'actor_visible_messages': deepcopy(row['payload']['messages']),
                'candidate': deepcopy(candidate),
                'proposal_status': ('text_only' if candidate is None and row['status'] == 'interface_valid' else row['status']),
                'context_completeness': 'Exact actor payload messages and tools; only requested_model and requested_settings omitted. No future outcome or private evaluator/user instructions added.',
                'decision': None,
            }
            dump(self.root / 'review_packets' / (packet_id + '.json'), packet)
            supplement = {'packet_id': packet_id, 'execution_status': 'not_executed' if candidate else 'not_applicable',
                          'guard_decision': None, 'authorization_decision': None,
                          'state_change': None, 'native_result': None}
            dump(self.root / 'outcome_supplements' / (packet_id + '.json'), supplement)
            if not any(r['packet_id'] == packet_id for r in self.packet_index):
                self.packet_index.append({'packet_id': packet_id, 'generation_id': row['generation_id'],
                                          'proposal_group_id': row['proposal_group_id'], 'group_index': index})
            if candidate is not None:
                self.packet_by_call[candidate['id']] = packet_id
        self.save_generations()

    def finish_generation(self, status, *, error=None):
        row = self.pending
        if row is None:
            return
        row['status'] = status
        if error is not None:
            row['exception_type'], row['error'] = type(error).__name__, str(error)
        row['candidate_count'] = len(row.get('proposal', {}).get('tool_calls', [])) if status == 'interface_valid' else 0
        if row['role'] == 'actor':
            self.write_packets(row)
        self.event('generation_finished', generation_id=row['generation_id'], role=row['role'], status=status)
        self.save_generations()
        self.pending = None

    def instrument(self, environment):
        original_response = environment.get_response
        original_setup = environment.run_env_function_call

        def execute(function, proposal, *, setup_action=False):
            self.check_deadline()
            before = self.snapshot(environment)
            setup = self.phase == 'setup'
            kind = 'setup_initialization_action' if setup_action else ('setup_history_replay' if setup else 'runtime_tool')
            execution_id = uuid.uuid4().hex
            packet_id = None if setup or getattr(proposal, 'requestor', None) != 'assistant' else self.packet_by_call.get(getattr(proposal, 'id', None))
            origin = kind if setup else ('actor_proposal' if packet_id else ('user_proposal' if getattr(proposal, 'requestor', None) == 'user' else 'initial_history_pending'))
            self.event('tool_execution_started', execution_id=execution_id, execution_kind=kind,
                       packet_id=packet_id, tool_origin=origin, proposal=plain(proposal), before_sha256=before,
                       guard_decision='not_applied', execution_policy='native_baseline_simulation', authorization_decision=None)
            result = None
            error = None
            try:
                result = function(proposal)
                return result
            except Exception as exc:
                error = exc
                raise
            finally:
                after = self.snapshot(environment)
                failed = error is not None or bool(getattr(result, 'error', False))
                if setup:
                    self.setup_execution_count += 1
                else:
                    self.execution_count += 1
                    self.actor_execution_count += int(packet_id is not None)
                    self.nonactor_execution_count += int(packet_id is None)
                    self.tool_error_count += int(failed)
                supplement = {'packet_id': packet_id,
                              'execution_status': 'exception' if error else ('native_tool_error' if failed else 'executed'),
                              'guard_decision': 'not_applied', 'execution_policy': 'native_baseline_simulation',
                              'tool_origin': origin, 'authorization_decision': None,
                              'state_change': {'before_sha256': before, 'after_sha256': after, 'changed': before != after},
                              'native_result': plain(result), 'error': None if error is None else {'type': type(error).__name__, 'message': str(error)}}
                self.event('tool_execution_finished', execution_id=execution_id, execution_kind=kind, **supplement)
                if packet_id is not None:
                    dump(self.root / 'outcome_supplements' / (packet_id + '.json'), supplement)

        environment.get_response = lambda proposal: execute(original_response, proposal)
        environment.run_env_function_call = lambda proposal: execute(original_setup, proposal, setup_action=True)


class RecordingTransport:
    def __init__(self, delegate, journal):
        self.delegate, self.journal = delegate, journal

    def generate(self, role, payload):
        self.journal.start_generation(role, payload)
        try:
            remaining = self.journal.check_deadline()
            if hasattr(self.delegate, 'per_attempt_seconds'):
                self.delegate.per_attempt_seconds = min(self.delegate.per_attempt_seconds, remaining)
            proposal = self.delegate.generate(role, payload)
            self.journal.pending['proposal'] = deepcopy(proposal)
            self.journal.pending['status'] = 'returned'
            self.journal.event('generation_returned', generation_id=self.journal.pending['generation_id'])
            self.journal.save_generations()
            return proposal
        except Exception as exc:
            self.journal.finish_generation(failure_kind(exc), error=exc)
            raise


class AuditedOrchestrator(Orchestrator):
    def __init__(self, *args, journal, **kwargs):
        self.journal = journal
        super().__init__(*args, **kwargs)

    def initialize(self):
        self.journal.phase = 'setup'
        before = self.journal.snapshot(self.environment)
        self.journal.event('initialization_started', before_sha256=before)
        try:
            super().initialize()
        finally:
            after = self.journal.snapshot(self.environment)
            self.journal.event('initialization_finished', before_sha256=before, after_sha256=after, changed=before != after)
            self.journal.checkpoint(self, status='initialization_returned')
        self.journal.phase = 'runtime'

    def step(self):
        self.journal.check_deadline()
        self.journal.event('native_step_started', step_count=self.step_count,
                           from_role=plain(self.from_role), to_role=plain(self.to_role))
        try:
            result = super().step()
            self.journal.finish_generation('interface_valid')
            return result
        except Exception as exc:
            self.journal.finish_generation(failure_kind(exc), error=exc)
            self.journal.event('native_step_failed', exception_type=type(exc).__name__, error=str(exc))
            raise
        finally:
            self.journal.checkpoint(self, status='native_step_returned')


def ensure_deterministic_task(task):
    if task.evaluation_criteria and RewardType.NL_ASSERTION in task.evaluation_criteria.reward_basis:
        raise ValueError('Task requires NL_ASSERTION reward; model judges are forbidden in this pilot')


def run_episode(*, task, actor_model, user_model, actor_transport, user_transport,
                environment, output_root, episode_id, deadline, max_steps=24, max_errors=3):
    """Execute one supplied task; caller alone selects train tasks and transport."""
    ensure_deterministic_task(task)
    journal = EpisodeJournal(output_root, episode_id, policy=environment.get_policy(), deadline=deadline)
    journal.instrument(environment)
    actor = CodexLLMAgent(tools=environment.get_tools(), domain_policy=environment.get_policy(),
                          llm=actor_model, llm_args={}, transport=RecordingTransport(actor_transport, journal))
    user_tools = environment.get_user_tools() if environment.user_tools is not None else None
    user = CodexUserSimulator(tools=user_tools, instructions=str(task.user_scenario),
                              llm=user_model, llm_args={}, transport=RecordingTransport(user_transport, journal))
    orchestrator = AuditedOrchestrator(domain='retail', agent=actor, user=user, environment=environment,
                                      task=task, max_steps=max_steps, max_errors=max_errors, seed=None,
                                      solo_mode=False, validate_communication=True, journal=journal)
    report = {'status': 'running', 'episode_id': episode_id, 'task_id': task.id,
              'actor_model': actor_model, 'user_model': user_model,
              'native_reward_is_authorization_label': False}
    dump(journal.directory / 'result.json', report)
    try:
        simulation = orchestrator.run()
        dump(journal.directory / 'native_simulation.json', simulation)
        journal.checkpoint(orchestrator, status='native_simulation_completed')
        reward = evaluate_simulation(simulation, task, EvaluationType.ALL, solo_mode=False, domain='retail')
        dump(journal.directory / 'native_reward.json', {'evaluation_type': 'ALL', 'model_judge_used': False,
                                                     'authorization_label': None, 'reward_info': plain(reward)})
        report.update(status='completed', termination_reason=plain(simulation.termination_reason),
                      native_reward=reward.reward)
    except Exception as exc:
        report.update(status=failure_kind(exc), exception_type=type(exc).__name__, error=str(exc))
        journal.event('episode_failed', status=report['status'], exception_type=type(exc).__name__, error=str(exc))
    finally:
        journal.checkpoint(orchestrator, status=report['status'])
        report['funnel'] = journal.funnel()
        report['native_step_count'] = orchestrator.step_count
        dump(journal.directory / 'result.json', report)
    return report


def run_schedule(*, schedule, output_root, episode_runner, deadline):
    """Sequential fail-closed schedule. All planned episodes exist before attempt 1."""
    report = {'status': 'running', 'episodes': [dict(row, status='not_run') for row in schedule],
              'stop_rule': 'no retries; stop at first incomplete episode; preserve remaining not_run',
              'generalization_claim': 'none; two preselected training tasks, one repetition'}
    path = Path(output_root) / 'summary.json'
    dump(path, report)
    for entry in report['episodes']:
        if time.monotonic() >= deadline:
            report['status'], report['stop_reason'] = 'budget_exhausted', 'pilot wall-clock limit'
            break
        entry['status'] = 'running'
        dump(path, report)
        try:
            result = episode_runner(entry)
        except Exception as exc:
            result = {'status': failure_kind(exc), 'exception_type': type(exc).__name__, 'error': str(exc)}
        entry.update(result)
        dump(path, report)
        if entry['status'] != 'completed':
            report['status'], report['stop_reason'] = 'stopped', entry['status']
            break
    else:
        report['status'] = 'completed'
    report['funnel'] = {}
    for entry in report['episodes']:
        for key, value in entry.get('funnel', {}).items():
            report['funnel'][key] = report['funnel'].get(key, 0) + value
    report['episodes_completed'] = sum(e['status'] == 'completed' for e in report['episodes'])
    report['episodes_not_run'] = sum(e['status'] == 'not_run' for e in report['episodes'])
    dump(path, report)
    return report
