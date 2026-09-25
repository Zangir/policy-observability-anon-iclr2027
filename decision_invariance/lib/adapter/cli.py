"""Strict fresh-session Codex CLI transport. No episode launcher and no automatic retries.

The trusted harness mounts only CLI runtime/auth/config and one permitted payload
inside a fresh bubblewrap filesystem/PID namespace. HOME/CODEX_HOME values are not
changed. Authentication is never copied or logged. Backend identity remains unknown.
"""
from __future__ import annotations
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import tomllib
import uuid
from jsonschema import Draft202012Validator
from adapter.toolless_controls import BINARY_SHA256, VERSION, additional_arguments, bind_catalog, validate_catalog, assert_empty_inventory

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'content': {'type': ['string', 'null']},
        'tool_calls': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False,
            'properties': {'id': {'type':'string','minLength':1},
                           'name': {'type':'string','minLength':1},
                           'arguments_json': {'type':'string'}},
            'required': ['id','name','arguments_json']}},
    }, 'required':['content','tool_calls']}
DISABLED_FEATURES = ['shell_tool','unified_exec','view_image','apps','plugins','remote_plugin',
    'browser_use','browser_use_external','browser_use_full_cdp_access','computer_use',
    'in_app_browser','multi_agent','multi_agent_v2','memories','hooks','skill_search',
    'image_generation','code_mode','code_mode_host','tool_suggest','shell_snapshot',
    'shell_snapshot_v2','workspace_dependencies','enable_mcp_apps','sleep_tool',
    'in_app_local_automation','in_app_chat','chronicle','goals','request_permissions_tool']
ALLOWED_ITEM_TYPES = {'agent_message','reasoning','plan'}

class TransportError(RuntimeError):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def strict_json(text):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise TransportError('duplicate JSON key: '+k)
            out[k] = v
        return out
    def reject_constant(value):
        raise TransportError('nonfinite JSON number: '+value)
    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=reject_constant)
    except (ValueError, TypeError) as e:
        raise TransportError('malformed JSON') from e


def validate_wire(raw, tools, seen_ids):
    value = strict_json(raw)
    errors = list(Draft202012Validator(SCHEMA).iter_errors(value))
    if errors:
        raise TransportError('proposal schema: '+errors[0].message)
    known = {t['function']['name']:t['function'] for t in tools}
    calls=[]
    new_ids=set()
    for t in value['tool_calls']:
        if t['id'] in seen_ids or t['id'] in new_ids:
            raise TransportError('duplicate call ID')
        if t['name'] not in known:
            raise TransportError('unknown native tool')
        args = strict_json(t['arguments_json'])
        if not isinstance(args, dict):
            raise TransportError('arguments must be an object')
        errors = list(Draft202012Validator(known[t['name']].get('parameters',{})).iter_errors(args))
        extra=set(args)-set(known[t['name']].get('parameters',{}).get('properties',{}))
        if errors or extra:
            raise TransportError('tool arguments schema: '+(errors[0].message if errors else 'unexpected fields'))
        new_ids.add(t['id'])
        calls.append({'id':t['id'],'name':t['name'],'arguments':args})
    has_text=isinstance(value['content'],str) and bool(value['content'].strip())
    if has_text==bool(calls):
        raise TransportError('exactly one of text or tool calls required')
    seen_ids.update(new_ids)
    return {'content':value['content'],'tool_calls':calls}


def validate_events(raw):
    events=[]
    for line in raw.splitlines():
        if not line.strip():
            continue
        event = strict_json(line)
        if not isinstance(event,dict):
            raise TransportError('non-object CLI event')
        typ=event.get('type','')
        if typ in {'error','turn.failed'}:
            raise TransportError('CLI reported failure')
        if typ.startswith('item.'):
            item=event.get('item',{})
            if item.get('type') not in ALLOWED_ITEM_TYPES:
                raise TransportError('forbidden or unknown host-tool event: '+str(item.get('type')))
        elif typ not in {'thread.started','turn.started','turn.completed'}:
            raise TransportError('unknown CLI event: '+typ)
        events.append(event)
    if not any(e.get('type')=='turn.completed' for e in events):
        raise TransportError('missing completed turn (truncated events)')
    return events


def native_binary():
    binary=ROOT/'environment/codex-cli'/VERSION/'node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex'
    if not binary.is_file():
        raise TransportError('pinned project-local Codex binary missing')
    return binary


def context_paths():
    home=Path.home()
    codex_home=Path(os.environ.get('CODEX_HOME',str(home/'.codex')))
    return home,codex_home


def sandbox_command(run_dir, command, *, include_auth=True):
    run_dir=Path(run_dir).resolve()
    home,codex_home=context_paths()
    binary=native_binary()
    cmd=['bwrap','--die-with-parent','--new-session','--unshare-user','--unshare-pid',
         '--unshare-ipc','--unshare-uts','--cap-drop','ALL',
         '--ro-bind','/usr','/usr','--symlink','usr/bin','/bin',
         '--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64',
         '--proc','/proc','--dev','/dev','--tmpfs','/tmp',
         '--dir',str(home),'--dir',str(codex_home),
         '--ro-bind',str(binary),'/opt/codex','--dir','/work',
         '--bind',str(run_dir),'/exchange','--chdir','/work']
    for src in ['/etc/ssl/certs','/etc/resolv.conf','/etc/hosts','/etc/nsswitch.conf', '/etc/passwd','/etc/group']:
        if Path(src).exists():
            cmd+=['--ro-bind',src,src]
    # Preserve site requirements if present; no bypass/ignore flags.
    if Path('/etc/codex').exists():
        cmd+=['--ro-bind','/etc/codex','/etc/codex']
    for name in ['config.toml','rules'] + (['auth.json'] if include_auth else []):
        src=codex_home/name
        if src.exists():
            cmd+=['--ro-bind',str(src),str(src)]
    return bind_catalog(cmd+['--']+command, ROOT/'configs/cli_model_catalog.json')


def clean_environment():
    # Preserve configured home values verbatim, never modify process-global env.
    keys=['HOME','CODEX_HOME','LANG','LC_ALL','TZ','SSL_CERT_FILE','SSL_CERT_DIR']
    result={k:os.environ[k] for k in keys if k in os.environ}
    result['PATH']='/usr/bin:/bin'
    return result


def cli_arguments(model):
    _,codex_home=context_paths()
    user_path=codex_home/'config.toml'
    user=tomllib.loads(user_path.read_text()) if user_path.exists() else {}
    if 'q07_openai' in user.get('model_providers',{}):
        raise TransportError('project provider alias collides with user configuration')
    args=['/opt/codex','exec','--strict-config','--ephemeral','--skip-git-repo-check',
          '--sandbox','read-only','--json','--color','never','--model',model,
          '--output-schema','/exchange/schema.json','--output-last-message','/exchange/final.txt',
          '-c','approval_policy="never"','-c','web_search="disabled"',
          '-c','skills.include_instructions=false','-c','project_doc_max_bytes=0',
          '-c','allow_login_shell=false','-c','features.skip_host_skill_discovery=true',
          '-c','model_reasoning_effort="low"','-c','model_reasoning_summary="none"',
          '-c','suppress_unstable_features_warning=true',
          '-c','model_provider="q07_openai"',
          '-c','model_providers.q07_openai.name="OpenAI"',
          '-c','model_providers.q07_openai.wire_api="responses"',
          '-c','model_providers.q07_openai.requires_openai_auth=true',
          '-c','model_providers.q07_openai.request_max_retries=0',
          '-c','model_providers.q07_openai.stream_max_retries=0',
          '-c','model_providers.q07_openai.supports_websockets=false',
          '-c','model_providers.q07_openai.supports_standalone_web_search=true',
          '-c','model_providers.q07_openai.http_headers.version="0.155.1"',
          '-c','model_providers.q07_openai.env_http_headers."OpenAI-Organization"="OPENAI_ORGANIZATION"',
          '-c','model_providers.q07_openai.env_http_headers."OpenAI-Project"="OPENAI_PROJECT"']
    for name in DISABLED_FEATURES:
        args+=['--disable',name]
    for name in user.get('mcp_servers',{}):
        if not __import__('re').fullmatch(r'[A-Za-z0-9_-]+',name):
            raise TransportError('MCP name needs explicit CLI key handling')
        args+=['-c','mcp_servers.'+name+'.enabled=false']
    validate_catalog(ROOT/'configs/cli_model_catalog.json', model)
    return args+additional_arguments()+['-']


def configuration_fingerprint(model):
    _,codex_home=context_paths()
    paths=[codex_home/'config.toml',Path('/etc/codex/config.toml'),Path('/etc/codex/requirements.toml')]
    for root in [codex_home/'rules',Path('/etc/codex')]:
        if root.exists():paths.extend(p for p in root.rglob('*') if p.is_file())
    # Hash configuration only; authentication contents and hashes are excluded.
    return {'model':model,'argv':cli_arguments(model),
            'tool_controls_sha256':sha(ROOT/'adapter/toolless_controls.py'),
            'inventory_verifier_sha256':sha(ROOT/'adapter/inventory_gate.py'),
            'model_catalog_sha256':sha(ROOT/'configs/cli_model_catalog.json'),
            'config_sha256':{str(p):sha(p) for p in sorted(set(paths)) if p.is_file()},
            'transport_sha256':sha(Path(__file__)),
            'schema_sha256':hashlib.sha256(json.dumps(SCHEMA,sort_keys=True).encode()).hexdigest()}


def verify_isolation_evidence(gate,model):
    required={'allowed','canary_denial','research_denial','host_process_denial',
              'version','authentication','strict_features','disabled_mcp','catalog_controls','serialized_tool_inventory'}
    checks={c.get('name'):c.get('passed') for c in gate.get('checks',[])}
    if (gate.get('status')!='passed' or not required.issubset(checks)
        or not all(checks[k] is True for k in required)
        or gate.get('binary_sha256')!=BINARY_SHA256
        or gate.get('binary_sha256')!=sha(native_binary())
        or gate.get('configuration_fingerprint')!=configuration_fingerprint(model)):
        raise TransportError('isolation gate missing, failed, or stale')
    proof=gate.get('tool_inventory_evidence',{})
    try:
        request_path=ROOT/proof['request_path']
        if sha(request_path)!=proof['request_sha256']:
            raise ValueError('captured tool request changed')
        assert_empty_inventory(strict_json(request_path.read_text()),model)
        from adapter.inventory_gate import verify_capture
        verified=verify_capture(request_path.parent.parent,model,configuration_fingerprint(model),
                                BINARY_SHA256,sha(ROOT/'configs/cli_model_catalog.json'),
                                sha(ROOT/'adapter/toolless_controls.py'))
        if verified['summary_sha256']!=proof['capture_summary_sha256']:
            raise ValueError('capture summary changed')
        if proof.get('configuration_fingerprint')!=configuration_fingerprint(model):
            raise ValueError('tool inventory configuration changed')
    except (KeyError, ValueError, OSError) as exc:
        raise TransportError('serialized tool inventory missing, unsafe, or stale') from exc


def run_process(argv, prompt, run_dir, timeout=180):
    if not 0 < timeout <= 180:
        raise ValueError('attempt timeout must be within (0,180]')
    run_dir=Path(run_dir)
    start=time.monotonic()
    termination='exit'
    with (run_dir/'events.jsonl').open('wb') as out, (run_dir/'stderr.txt').open('wb') as err:
        try:
            proc=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=out,stderr=err,
                                  env=clean_environment(),start_new_session=True)
            try:
                cleanup_reserve=min(3.0, timeout/10)
                proc.communicate(prompt.encode(),timeout=max(0,timeout-cleanup_reserve-(time.monotonic()-start)))
                rc=proc.returncode
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid,signal.SIGTERM)
                try:proc.wait(timeout=max(0,timeout-(time.monotonic()-start)))
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid,signal.SIGKILL);proc.wait()
                rc,termination=124,'timeout'
        except OSError as e:
            err.write((type(e).__name__+': '+str(e)).encode())
            rc,termination=127,'launch_error'
    return {'exit_status':rc,'termination_reason':termination,'elapsed_seconds':time.monotonic()-start}


class CodexTransport:
    def __init__(self, *, model, output_dir, isolation_evidence, budget_file=None, phase='smoke', release_file=None):
        self.model=model
        self.output_dir=Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True,exist_ok=True)
        self.isolation_evidence=Path(isolation_evidence).resolve()
        self.budget_file=Path(budget_file or ROOT/'outputs/smoke_budget.json')
        self.seen_ids={'actor':set(),'user_simulator':set()}
        self.phase=phase
        self.max_attempts=8
        self.max_elapsed_seconds=1200
        self.per_attempt_seconds=180
        self.release_file=None
        self.release_sha256=None
        self.release_artifacts={}
        if phase=='training_pilot':
            if release_file is None:
                raise TransportError('pilot transport requires a frozen release')
            self.release_file=Path(release_file).resolve()
            release=strict_json(self.release_file.read_text())
            if release.get('phase')!='training_pilot' or release.get('user_authorization_date')!='2026-09-19':
                raise TransportError('wrong pilot phase or authorization')
            if release.get('config_sha256')!=sha(ROOT/'configs/training_pilot_v1.json'):
                raise TransportError('pilot config changed')
            if model not in release.get('models',[]):
                raise TransportError('model outside pilot release')
            limits=release.get('limits',{})
            caps={'max_attempts':120,'max_elapsed_seconds':3600,'per_attempt_seconds':180}
            for name,cap in caps.items():
                value=limits.get(name)
                if type(value) is not int or not 0 < value <= cap:
                    raise TransportError('invalid pilot '+name)
                setattr(self,name,value)
            expected_budget=(ROOT/release['budget_file']).resolve()
            expected_output=(ROOT/release['output_root']).resolve()
            if (not expected_output.is_relative_to(ROOT/'outputs') or expected_output==ROOT/'outputs'
                or not expected_budget.is_relative_to(expected_output)
                or self.budget_file.resolve()!=expected_budget
                or not self.output_dir.is_relative_to(expected_output)):
                raise TransportError('pilot output/budget paths differ from release')
            artifacts=release.get('artifacts',{})
            required={'adapter/cli.py','adapter/native.py','adapter/toolless_controls.py','adapter/inventory_gate.py',
                      'configs/cli_model_catalog.json','configs/training_pilot_v1.json','scripts/run_training_pilot.py'}
            if not required.issubset(artifacts):
                raise TransportError('pilot release lacks required artifact hashes')
            for name,expected in artifacts.items():
                if sha(ROOT/name)!=expected:
                    raise TransportError('pilot release artifact changed: '+name)
            self.release_sha256=sha(self.release_file)
            self.release_artifacts=dict(artifacts)
        elif phase!='smoke' or release_file is not None:
            raise TransportError('unknown transport phase or unexpected release')


    def _verify_release(self):
        if self.release_file is not None:
            if sha(self.release_file)!=self.release_sha256:
                raise TransportError('pilot release changed during execution')
            for name,expected in self.release_artifacts.items():
                if sha(ROOT/name)!=expected:
                    raise TransportError('pilot release artifact changed during execution: '+name)

    def generate(self,role,payload):
        if role not in self.seen_ids:
            raise TransportError('unsupported role')
        if set(payload)-{'messages','tools','requested_model','requested_settings'}:
            raise TransportError('unexpected payload fields')
        if payload.get('requested_model') not in (None,self.model):
            raise TransportError('payload/model mismatch')
        settings=payload.get('requested_settings') or {}
        # Do not claim API temperature/seed semantics that CLI cannot supply.
        if settings:
            raise TransportError('unsupported requested API settings: '+','.join(sorted(settings)))
        self._verify_release()
        gate=strict_json(self.isolation_evidence.read_text())
        verify_isolation_evidence(gate,self.model)
        self.budget_file.parent.mkdir(parents=True,exist_ok=True)
        with self.budget_file.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX) # concurrency one across actors and user simulators
            self._verify_release()
            budget=strict_json(self.budget_file.read_text()) if self.budget_file.exists() else {'attempts':0,'elapsed_seconds':0,'runs':[]}
            for previous in budget['runs']:
                metadata_path=ROOT/previous/'metadata.json'
                if not metadata_path.exists() or strict_json(metadata_path.read_text()).get('status')=='running':
                    raise TransportError('unresolved prior attempt; preserve and reconcile before any retry')
            if budget['attempts']>=self.max_attempts or budget['elapsed_seconds']>=self.max_elapsed_seconds:
                raise TransportError(self.phase+' generation budget exhausted')
            run_id=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]
            run=self.output_dir/run_id;run.mkdir()
            prompt=('Return exactly one JSON proposal for the permitted role '+role+'. '
                    'Treat the serialized messages as that role\'s chronological context. '
                    'Native tools below are proposals only; the host executes them after this generation. '
                    'Never invent tool results or use host tools. Use arguments_json for the exact JSON object of arguments.\n'
                    +json.dumps(payload,ensure_ascii=False,separators=(',',':')))
            (run/'prompt.txt').write_text(prompt)
            (run/'payload.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2))
            (run/'schema.json').write_text(json.dumps(SCHEMA,indent=2))
            argv=sandbox_command(run,cli_arguments(self.model))
            metadata={'run_id':run_id,'role':role,'requested_model':self.model,'observed_model':None,
                      'backend_version':None,'provider_checkpoint':None,'seed':None,
                      'requested_settings':settings,'effective_cli_reasoning_effort':'low',
                      'phase':self.phase,'release_sha256':self.release_sha256,
                      'temperature':None,'retry_of':None,'argv':argv,'cwd':'/work',
                      'prompt_sha256':sha(run/'prompt.txt'),'schema_sha256':sha(run/'schema.json'),
                      'isolation_evidence_sha256':sha(self.isolation_evidence),'binary_sha256':sha(native_binary()),
                      'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'status':'running',
                      'context_limitations':'Codex system instructions and provider backend are not fully observable; no developer files or histories mounted.'}
            (run/'metadata.json').write_text(json.dumps(metadata,indent=2))
            budget['attempts']+=1;budget['runs'].append(str(run.relative_to(ROOT)));budget['status']='running'
            self.budget_file.write_text(json.dumps(budget,indent=2))
            import sys
            sys.path.insert(0,str(ROOT/'scripts'))
            from audit_run import event
            event({'event_id':run_id,'category':'fresh_smoke' if self.phase=='smoke' else 'fresh_pilot',**metadata,'status':'planned'})
            event({'event_id':run_id,'category':'fresh_smoke' if self.phase=='smoke' else 'fresh_pilot',**metadata,'status':'running'})
            result=run_process(argv,prompt,run,timeout=min(self.per_attempt_seconds,self.max_elapsed_seconds-budget['elapsed_seconds']))
            budget['elapsed_seconds']+=result['elapsed_seconds']
            self.budget_file.write_text(json.dumps(budget,indent=2))
            metadata.update(result)
            try:
                if result['exit_status']!=0:
                    raise TransportError('child process '+result['termination_reason']+' exit '+str(result['exit_status']))
                events=validate_events((run/'events.jsonl').read_text())
                metadata['exposed_usage']=[e.get('usage') for e in events if e.get('type')=='turn.completed']
                observed={e.get('model') for e in events if e.get('model')}
                metadata['observed_model']=sorted(observed) or None
                answer=validate_wire((run/'final.txt').read_text(),payload.get('tools',[]),self.seen_ids[role])
                (run/'validated.json').write_text(json.dumps(answer,indent=2))
                metadata['status']='succeeded'
            except Exception as exc:
                metadata.update(status='failed',error=type(exc).__name__+': '+str(exc))
                raise
            finally:
                metadata['artifact_sha256']={p.name:sha(p) for p in run.iterdir() if p.is_file() and p.name!='metadata.json'}
                (run/'metadata.json').write_text(json.dumps(metadata,indent=2))
                budget['status']=metadata['status']
                budget['status_scope']='last_attempt'
                self.budget_file.write_text(json.dumps(budget,indent=2))
                import sys
                sys.path.insert(0,str(ROOT/'scripts'))
                from audit_run import event,note
                event({'event_id':run_id, 'run_id':run_id,'category':'fresh_smoke' if self.phase=='smoke' else 'fresh_pilot',**metadata,
                       'stdout_path':str(run/'events.jsonl'),'stderr_path':str(run/'stderr.txt')})
                note('Fresh CLI '+self.phase+' '+run_id+': '+metadata['status']+'; '+str(run.relative_to(ROOT))+'/metadata.json. '+('Interface evidence only.' if self.phase=='smoke' else 'Training-only pilot; not a confirmatory estimate.'))
            return answer
