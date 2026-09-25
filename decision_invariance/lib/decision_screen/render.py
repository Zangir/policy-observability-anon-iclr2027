"""Lossless, outcome-independent projection and rendering of frozen packets."""
from __future__ import annotations
import collections
import hashlib
import json
import math
from pathlib import Path

FIELDS = ('group_index', 'group_size', 'policy_text', 'tool_schemas',
          'actor_visible_messages', 'candidate', 'context_completeness')
REMOVED = {'packet_version', 'packet_id', 'proposal_group_id', 'policy_sha256',
           'proposal_status', 'decision'}
MUTATIONS = {'cancel_pending_order', 'modify_pending_order_address',
             'modify_pending_order_payment', 'modify_pending_order_items',
             'modify_user_address', 'return_delivered_order_items',
             'exchange_delivered_order_items'}
READS = {'calculate', 'find_user_id_by_email', 'find_user_id_by_name_zip',
         'get_user_details', 'get_order_details', 'get_product_details', 'get_item_details'}
ROOT = Path(__file__).resolve().parents[1]
COHORTS = {
    'v2': ('outputs/retail_pilot_20260919_v2',
           'audit/retail_v2_20260919/assistant_adjudication/review_order.json', 55, 33),
    'v1': ('outputs/training_pilot_20260919',
           'audit/pilot_20260919/assistant_adjudication/review_order.json', 43, 19),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError('duplicate JSON key: ' + key)
            out[key] = value
        return out
    def constant(value):
        raise ValueError('nonfinite JSON: ' + value)
    def number(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError('overflowing JSON float')
        return parsed
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant, parse_float=number)


def typed_tree(value):
    if value is None:
        return ('null',)
    if type(value) is bool:
        return ('bool', value)
    if type(value) is int:
        return ('int', str(value))
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError('nonfinite float')
        return ('float', value.hex())
    if type(value) is str:
        return ('str', value)
    if type(value) is list:
        return ('array', tuple(typed_tree(v) for v in value))
    if type(value) is dict and all(type(k) is str for k in value):
        return ('object', tuple((k, typed_tree(value[k])) for k in sorted(value)))
    raise ValueError('unsupported semantic value: ' + str(type(value)))


def canonical(value):
    if isinstance(value, dict):
        return {key: canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [canonical(v) for v in value]
    return value


def encode(value):
    typed_tree(value)
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def project(packet):
    if set(packet) != set(FIELDS) | REMOVED:
        raise ValueError('unexpected packet fields: ' + str(set(packet) ^ (set(FIELDS) | REMOVED)))
    if packet['candidate'] is None or packet['proposal_status'] != 'interface_valid':
        raise ValueError('screening requires an existing typed valid proposal')
    if packet['decision'] is not None:
        raise ValueError('source packet contains a decision')
    if sha(packet['policy_text'].encode()) != packet['policy_sha256']:
        raise ValueError('policy string hash mismatch')
    candidate = packet['candidate']
    if set(candidate) != {'id', 'name', 'arguments'} or not isinstance(candidate['arguments'], dict):
        raise ValueError('invalid native candidate shape')
    for message in packet['actor_visible_messages']:
        if set(message) - {'role', 'content', 'tool_calls', 'tool_call_id'}:
            raise ValueError('unexpected history metadata')
        if message['role'] not in {'system', 'user', 'assistant', 'tool'}:
            raise ValueError('unexpected history role')
    # Iteration order is the immutable original packet object order.
    projected = {k: v for k, v in packet.items() if k in FIELDS}
    typed_tree(projected)
    return projected


def render(packet):
    semantic = project(packet)
    c = canonical(semantic)
    k = {'candidate': c['candidate'], **{key: value for key, value in c.items() if key != 'candidate'}}
    arms = {'R': encode(semantic), 'C': encode(c), 'K': encode(k)}
    expected = typed_tree(semantic)
    for raw in arms.values():
        decoded = strict_json(raw)
        if typed_tree(decoded) != expected:
            raise ValueError('type-aware semantic roundtrip mismatch')
        for name in ['policy_text', 'tool_schemas', 'actor_visible_messages', 'candidate']:
            if typed_tree(decoded[name]) != typed_tree(packet[name]):
                raise ValueError('semantic source field changed: ' + name)
    return arms


def effect(name):
    if name in MUTATIONS:
        return 'mutation'
    if name in READS:
        return 'read'
    if name == 'transfer_to_human_agents':
        return 'transfer'
    raise ValueError('undeclared native tool effect: ' + name)


def inventory(cohort, root=ROOT):
    directory, order_path, expected_typed, expected_null = COHORTS[cohort]
    directory = root / directory
    order = strict_json((root/order_path).read_bytes())
    entries = order['packets']
    provenance = {order_path: sha((root/order_path).read_bytes())}
    mapping = {}
    # Only task/episode and packet membership are consumed from trusted records.
    # Native rewards, assistant labels and outcomes are never used for selection.
    for episode in sorted((directory/'internal/episodes').iterdir()):
        result_path = episode/'result.json'
        index_path = episode/'packet_index.json'
        result = strict_json(result_path.read_bytes())
        task = str(result['task_id'])
        for entry in strict_json(index_path.read_bytes()):
            if entry['packet_id'] in mapping:
                raise ValueError('duplicate packet ownership')
            mapping[entry['packet_id']] = (task, episode.name)
        for path in [result_path, index_path]:
            provenance[str(path.relative_to(root))] = sha(path.read_bytes())
    records = []
    null_count = 0
    seen = set()
    for entry in entries:
        path = root/entry['path']
        raw = path.read_bytes()
        if sha(raw) != entry['sha256']:
            raise ValueError('original frozen packet hash mismatch')
        packet = strict_json(raw)
        pid = packet['packet_id']
        if pid != entry['packet_id'] or pid in seen:
            raise ValueError('packet identity mismatch/duplicate')
        seen.add(pid)
        provenance[entry['path']] = entry['sha256']
        if packet['candidate'] is None:
            null_count += 1
            continue
        project(packet)
        task, episode = mapping[pid]
        records.append({'packet_id': pid, 'packet_sha256': entry['sha256'],
                        'packet_path': entry['path'], 'cohort': cohort,
                        'source_task': task, 'episode_id': episode,
                        'action_effect': effect(packet['candidate']['name']),
                        'tool_name': packet['candidate']['name'], 'packet': packet})
    if len(records) != expected_typed or null_count != expected_null or seen != set(mapping):
        raise ValueError('source cohort denominator mismatch')
    return records, provenance, null_count


def packet_order(records):
    groups = collections.defaultdict(list)
    for record in records:
        groups[record['source_task']].append(record)
    for task in groups:
        groups[task].sort(key=lambda r: r['packet_sha256'])
    mini = []
    if {r['cohort'] for r in records} == {'v2'}:
        for task in sorted(groups, key=int):
            first = groups[task][0]
            second = next((r for r in groups[task][1:] if r['episode_id'] != first['episode_id']), groups[task][1])
            mini.extend([first, second])
    chosen = {r['packet_sha256'] for r in mini}
    queues = {task: [r for r in rows if r['packet_sha256'] not in chosen] for task, rows in groups.items()}
    balanced = []
    while any(queues.values()):
        for task in sorted(queues, key=int):
            if queues[task]:
                balanced.append(queues[task].pop(0))
    # Mini is also task-balanced: one selected packet per task, then the second.
    if mini:
        mini = mini[::2] + mini[1::2]
    return mini + balanced, chosen
