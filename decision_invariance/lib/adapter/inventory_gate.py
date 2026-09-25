"""Draft gate verifier for post-integration inert request captures.

The parent may adopt this helper into scripts/; no inference or evidence mutation.
"""
import hashlib
import json
from pathlib import Path

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def verify_capture(run_directory, model, fingerprint, expected_binary_sha256,
                   expected_catalog_sha256, expected_controls_sha256):
    from adapter.toolless_controls import assert_empty_inventory
    run=Path(run_directory)
    summary=json.loads((run/'summary.json').read_text())
    if (summary.get('status')!='passed' or summary.get('integrated_transport') is not True
        or summary.get('original_catalog_negative_control') is not False
        or summary.get('model_inferences')!=0 or summary.get('real_auth_mounted') is not False
        or summary.get('binary_sha256')!=expected_binary_sha256
        or summary.get('catalog_sha256')!=expected_catalog_sha256
        or summary.get('controls_module_sha256')!=expected_controls_sha256):
        raise ValueError('capture is failed, stale, unintegrated, or not an inert fixture')
    matches=[item for item in summary['results'] if item['model']==model]
    if len(matches)!=1:
        raise ValueError('missing or duplicate model capture')
    item=matches[0]
    metadata_path=run/model/'metadata.json'
    if item.get('metadata_sha256')!=digest(metadata_path):
        raise ValueError('capture metadata hash changed')
    metadata=json.loads(metadata_path.read_text())
    if (metadata.get('passed') is not True or metadata.get('requests_captured')!=1
        or metadata.get('errors') or metadata.get('fingerprint_unchanged_after_capture') is not True
        or metadata.get('configuration_fingerprint')!=fingerprint):
        raise ValueError('capture invocation fingerprint is stale or incomplete')
    for name,expected in metadata['artifacts_sha256'].items():
        if Path(name).name!=name or digest(run/model/name)!=expected:
            raise ValueError('capture artifact hash changed')
    request_path=run/model/'request-1.json'
    if 'request-1.json' not in metadata['artifacts_sha256']:
        raise ValueError('request hash was not retained')
    assert_empty_inventory(json.loads(request_path.read_text()),model)
    return {'passed':True,'model':model,'run_directory':str(run),
            'summary_sha256':digest(run/'summary.json'),
            'metadata_sha256':digest(metadata_path),
            'request_sha256':digest(request_path),'tool_count':0,
            'method':'exact binary inert request capture plus pinned-source provider equivalence review'}
