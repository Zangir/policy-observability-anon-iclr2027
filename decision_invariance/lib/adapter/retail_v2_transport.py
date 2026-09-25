"""Separate v2 release validator; reuse unchanged CLI generation and isolation controls."""
from pathlib import Path
import json
import hashlib
from adapter.cli import CodexTransport, TransportError, ROOT, sha, strict_json

CONFIG_PATH = 'configs/retail_pilot_v2.json'
PHASE = 'retail_pilot_v2'
EXPECTED_CONFIG = {'schema_version': 2,
 'phase': 'retail_pilot_v2',
 'domain': 'retail',
 'split': 'train',
 'task_ids': ['0', '29', '34'],
 'actor_models': ['gpt-5.6-luna', 'gpt-5.6-sol', 'gpt-6-astra'],
 'user_model': 'gpt-5.6-sol',
 'repetitions': 1,
 'concurrency': 1,
 'episode_order': 'task_outer_actor_inner',
 'max_steps': 48,
 'max_errors': 3,
 'limits': {'max_attempts': 270, 'max_elapsed_seconds': 3600, 'per_attempt_seconds': 180},
 'llm_args_agent': {},
 'llm_args_user': {},
 'seed': None,
 'cli_reasoning_effort': 'low',
 'native_evaluation_type': 'ALL',
 'model_judge_allowed': False,
 'automatic_retries': 0,
 'stop_on_incomplete_episode': True,
 'source_dir': 'sources/tau2-bench-verified',
 'data_dir': 'sources/tau2-bench-verified/data',
 'retail_data_dir': 'sources/tau2-bench-verified/data/tau2/domains/retail',
 'benchmark_commit': '864350a8971a8f8ee9e7b8472e2edc380a806b0c',
 'benchmark_variant': '0.2.1.dev0+q07q08.retailfix1',
 'variant_report': 'audit/retail_fix_20260919/result.json',
 'output_root': 'outputs/retail_pilot_20260919_v2',
 'budget_file': 'outputs/retail_pilot_20260919_v2/generation_budget.json',
 'selection': 'Retain training IDs0,29. Add34, lowest numeric confirmed training ID whose expected '
              'mutating-action set is exactly modify_pending_order_address. Purposive development selection, '
              'not random.',
 'inference_claims': 'Fresh stochastic development episodes; no held-out estimate, ranking, causal cap '
                     'comparison, human ground truth, deterministic decoding or checkpoint-identity claim.'}
MODELS = EXPECTED_CONFIG['actor_models']
LIMITS = EXPECTED_CONFIG['limits']
COMMON_ARTIFACTS = {
    CONFIG_PATH, 'adapter/retail_v2_transport.py', 'scripts/run_retail_pilot_v2.py',
    'adapter/cli.py', 'adapter/native.py', 'adapter/pilot.py',
    'adapter/toolless_controls.py', 'adapter/inventory_gate.py', 'configs/cli_model_catalog.json',
}

def relative_path(name):
    if not isinstance(name, str) or Path(name).is_absolute() or '..' in Path(name).parts:
        raise TransportError('Release path must be project-relative without traversal')
    path = (ROOT / name).resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise TransportError('Release path escapes project')
    return path


def validate_config(config):
    # JSON byte semantics distinguish boolean/integer/float and reject extra keys.
    if not isinstance(config, dict) or json.dumps(config, sort_keys=True) != json.dumps(EXPECTED_CONFIG, sort_keys=True):
        raise TransportError('Frozen retail v2 configuration differs')
    for name in ('output_root', 'budget_file'):
        relative_path(config[name])
    return config


def validate_release_contract(release, config, required_artifacts=COMMON_ARTIFACTS):
    validate_config(config)
    if release.get('phase') != PHASE or release.get('user_authorization_date') != '2026-09-19':
        raise TransportError('Wrong retail v2 phase or authorization')
    if release.get('config_path') != CONFIG_PATH or release.get('config_sha256') != sha(ROOT / CONFIG_PATH):
        raise TransportError('Retail v2 config changed or wrong config binding')
    for key in ('output_root', 'budget_file', 'limits'):
        if json.dumps(release.get(key), sort_keys=True) != json.dumps(config[key], sort_keys=True):
            raise TransportError('Retail v2 release/config mismatch: ' + key)
    if release.get('models') != MODELS:
        raise TransportError('Retail v2 model set differs')
    artifacts = release.get('artifacts', {})
    if not isinstance(artifacts, dict) or not required_artifacts.issubset(artifacts):
        raise TransportError('Required retail v2 artifacts missing')
    for name, expected in artifacts.items():
        if not isinstance(expected, str) or len(expected) != 64 or sha(relative_path(name)) != expected:
            raise TransportError('Retail v2 release artifact changed: ' + name)
    return artifacts


class RetailV2Transport(CodexTransport):
    def __init__(self, *, model, output_dir, isolation_evidence, budget_file, release_file):
        release_file = Path(release_file).resolve()
        if not release_file.is_relative_to((ROOT / 'audit/retail_v2_20260919').resolve()):
            raise TransportError('Retail v2 release must be inside its audit directory')
        release_bytes = release_file.read_bytes()
        release_digest = hashlib.sha256(release_bytes).hexdigest()
        release = strict_json(release_bytes.decode())
        config = validate_config(strict_json((ROOT / CONFIG_PATH).read_text()))
        artifacts = validate_release_contract(release, config)
        if model not in MODELS:
            raise TransportError('Model outside retail v2 release')
        expected_output = relative_path(config['output_root'])
        expected_budget = relative_path(config['budget_file'])
        expected_calls = expected_output / 'calls'
        if Path(output_dir).resolve() != expected_calls or Path(budget_file).resolve() != expected_budget:
            raise TransportError('Retail v2 output/budget paths differ from frozen release')
        gates = release.get('isolation_evidence', {})
        if set(gates) != set(MODELS) or any(p not in artifacts for p in gates.values()):
            raise TransportError('Retail v2 isolation evidence not fully hash-bound')
        if Path(isolation_evidence).resolve() != relative_path(gates[model]):
            raise TransportError('Retail v2 supplied gate differs from release')
        # Base smoke initialization performs no inference and no budget reservation.
        # All v2 authorization/path/source checks above precede its mkdir side effect.
        super().__init__(model=model, output_dir=expected_calls,
                         isolation_evidence=isolation_evidence, budget_file=expected_budget)
        self.phase = PHASE
        self.max_attempts = LIMITS['max_attempts']
        self.max_elapsed_seconds = LIMITS['max_elapsed_seconds']
        self.per_attempt_seconds = LIMITS['per_attempt_seconds']
        self.release_file = release_file
        self.release_sha256 = release_digest
        self.release_artifacts = dict(artifacts)
        self._verify_release()
