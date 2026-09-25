"""Draft reviewed controls for official Codex 0.155.1; no execution on import."""
from pathlib import Path
import hashlib
import json

VERSION = '0.155.1'
BINARY_SHA256 = '0753dfe1d8b87a52436deb13eb1c549661ef4c84fee2c5aa688385eebeccb761'
SOURCE_COMMIT = 'be2951ea34f0d295ed0becf97079f92fa5f6950e'
CATALOG_TARGET = '/opt/q07_q08_model_catalog.json'
EXTRA_DISABLED_FEATURES = [
    'code_mode_only', 'deferred_executor', 'current_time_reminder',
    'token_budget', 'recommended_plugins', 'artifact', 'unbounded_connection_retries',
]
CONFIG_CONTROLS = {
    'tools.experimental_request_user_input.enabled': False,
    'tools.update_plan.enabled': False,
    'agents.enabled': False,
    'orchestrator.skills.enabled': False,
    'orchestrator.mcp.enabled': False,
}
MODEL_TOOL_VALUES = {
    'apply_patch_tool_type': None,
    'experimental_supported_tools': [],
    'supports_search_tool': False,
    'tool_mode': 'direct',
}

def additional_arguments():
    args=['-c', 'model_catalog_json='+json.dumps(CATALOG_TARGET)]
    for key,value in CONFIG_CONTROLS.items():
        args += ['-c',key+'='+json.dumps(value)]
    for name in EXTRA_DISABLED_FEATURES:
        args += ['--disable',name]
    return args

def bind_catalog(argv, catalog):
    """Add read-only mount before bwrap's command separator."""
    catalog=Path(catalog).resolve()
    index=argv.index('--')
    return argv[:index]+['--ro-bind',str(catalog),CATALOG_TARGET]+argv[index:]

def validate_catalog(catalog, model):
    value=json.loads(Path(catalog).read_text())
    entries=[item for item in value['models'] if item['slug']==model]
    if len(entries)!=1:
        raise ValueError('missing or duplicate requested catalog model')
    if any(entries[0].get(k)!=v for k,v in MODEL_TOOL_VALUES.items()):
        raise ValueError('model catalog enables host tool capability')
    return entries[0]

def validate_catalog_derivation(original, derived):
    """Ensure model identities/instructions/settings are untouched by isolation."""
    source=json.loads(Path(original).read_text())
    target=json.loads(Path(derived).read_text())
    if {k:v for k,v in source.items() if k!='models'} != {k:v for k,v in target.items() if k!='models'}:
        raise ValueError('catalog metadata changed outside tool controls')
    known={model['slug']:model for model in source['models']}
    if len(known)!=len(source['models']):
        raise ValueError('duplicate original catalog model')
    seen=set()
    for model in target['models']:
        slug=model['slug']
        if slug in seen or slug not in known:
            raise ValueError('unknown or duplicate derived model')
        seen.add(slug)
        expected=dict(known[slug]);expected.update(MODEL_TOOL_VALUES)
        if model!=expected:
            raise ValueError('catalog model changed outside tool controls')
    if not seen:
        raise ValueError('empty derived model catalog')
    return sorted(seen)

def tool_inventory(request):
    """Return every tool in both Responses and Responses Lite serialized forms.

    Reject absent declarations, ambiguity, or unexpected declaration types;
    a missing field must not silently become an empty tool list.
    """
    declared=[]
    if 'tools' in request and request['tools'] is not None:
        if not isinstance(request['tools'],list):
            raise ValueError('malformed top-level tools')
        declared.append(request['tools'])
    for item in request.get('input',[]):
        if not isinstance(item,dict):
            raise ValueError('malformed input item')
        if item.get('type')=='additional_tools':
            tools=item.get('tools')
            if not isinstance(tools,list):
                raise ValueError('malformed additional_tools')
            declared.append(tools)
    if len(declared)!=1:
        raise ValueError('expected exactly one explicit tool declaration')
    return declared[0]

def assert_empty_inventory(request, model):
    if request.get('model')!=model:
        raise ValueError('request model differs from required model')
    tools=tool_inventory(request)
    if tools:
        raise ValueError('serialized model request exposes host tools')
    return True
