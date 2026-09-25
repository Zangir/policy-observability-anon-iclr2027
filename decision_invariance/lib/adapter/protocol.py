"""Prospective rendering and blind-review plumbing; no empirical study runner."""
import hashlib
import json
from pathlib import Path
from jsonschema import Draft202012Validator
from adapter.cli import strict_json
SCHEMA=json.loads((Path(__file__).resolve().parents[1]/'schemas/visible_record.schema.json').read_text())
def canonical_bytes(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')
def canonical_hash(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
def validate(record):
    Draft202012Validator(SCHEMA).validate(record)
    seq=[h['sequence'] for h in record['history']]
    if seq!=sorted(set(seq)):
        raise ValueError('history chronology must be strictly increasing and unique')
    canonical_bytes(record)
def render(record, arm):
    validate(record)
    if arm=='generic_canonical':
        raw=canonical_bytes(record).decode()
    elif arm=='original_compact':
        raw=json.dumps(record,ensure_ascii=False,separators=(',',':'),allow_nan=False)
    elif arm=='pretty_keys':
        raw=json.dumps(record,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)
    elif arm=='candidate_first_keys':
        # Only ordering; no duplicate candidate, labels, schema explanation or new fields.
        keys=['candidate']+[k for k in sorted(record) if k!='candidate']
        raw=json.dumps({k:record[k] for k in keys},ensure_ascii=False,indent=2,allow_nan=False)
    else:raise ValueError('unknown rendering')
    if canonical_bytes(strict_json(raw))!=canonical_bytes(record):
        raise ValueError('typed record changed')
    return {'text':raw,'canonical_sha256':canonical_hash(record),
            'rendered_sha256':hashlib.sha256(raw.encode()).hexdigest(),
            'input_bytes':len(raw.encode()),'semantic_review':'pending'}
def blind_packet(record):
    validate(record)
    return {'review_id':canonical_hash(record),'record':record,'authorization_label':'pending',
            'governing_rule':None,'dialogue_evidence':None,'confidence':None,
            'reviewer_id':None,'uncertainty_reason':None}
