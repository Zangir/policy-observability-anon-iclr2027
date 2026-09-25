"""Prepare an immutable input cohort and complete conditional schedule before calls."""
from __future__ import annotations
import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import random
from decision_screen.render import ROOT, FIELDS, REMOVED, inventory, render, packet_order, sha
from adapter.decision_screen_transport import GUARD_INSTRUCTION, DECISION_SCHEMA, SETTINGS, item_identity, fingerprint, make_payload, make_prompt

SEED = 2026091901
MODELS = ['gpt-6-astra', 'gpt-5.6-sol']


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', default='audit/decision_screen_20260919/prepared')
    parser.add_argument('--config', default='configs/decision_screen_20260919.json')
    args = parser.parse_args()
    directory = ROOT/args.directory
    if directory.exists() or (ROOT/args.config).exists():
        raise ValueError('preparation output/config already exists; preserve and version drafts')
    directory.mkdir(parents=True)
    config = {
        'schema_version': 1, 'phase': 'decision_screen_20260919',
        'schedule_path': str((directory/'schedule.json').relative_to(ROOT)),
        'prepared_manifest_path': str((directory/'manifest.json').relative_to(ROOT)),
        'output_root': 'outputs/decision_screen_20260919',
        'guard_instruction': GUARD_INSTRUCTION, 'decision_schema': DECISION_SCHEMA,
        'models': MODELS, 'settings': SETTINGS, 'scheduler_seed': SEED,
        'max_attempts': 1176, 'per_attempt_seconds': 180,
        'dispatch_cutoff_utc': '2026-09-19T11:15:00Z',
        'drain_cutoff_utc': '2026-09-19T11:20:00Z',
        'reporting_cutoff_utc': '2026-09-19T11:25:00Z',
        'automatic_retries': 0, 'mini_workers': 2, 'max_workers': 4,
        'protocol_path': 'audit/decision_screen_20260919/PROTOCOL.md',
        'primary_contrast': ['K','C'], 'secondary_contrast': ['R','C'],
        'optional_extensions': 'secondary only after primary terminal and timing-only conservative ETA; archival only after both v2 blocks terminal and ETA; no outcome-adaptive selection',
        'unsupported_controls': ['provider_seed','temperature','served_checkpoint','output_token_limit'],
    }
    schedule = []; packets = []; sources = {}; cohort_counts = {}
    for cohort in ['v2','v1']:
        records, provenance, excluded = inventory(cohort)
        sources.update(provenance)
        ordered, mini = packet_order(records)
        by_hash = {}
        for row in ordered:
            arms = render(row['packet'])
            unique = {}; arm_map = {}
            for arm, raw in arms.items():
                digest = sha(raw)
                arm_map[arm] = digest
                if digest not in unique:
                    path = directory/'renderings'/(row['packet_sha256']+'_'+digest+'.json')
                    path.parent.mkdir(exist_ok=True)
                    path.write_bytes(raw)
                    wire = make_prompt(make_payload(raw.decode(), GUARD_INSTRUCTION))
                    unique[digest] = {'path': str(path.relative_to(ROOT)), 'sha256': digest,
                                      'bytes': len(raw), 'characters': len(raw.decode()),
                                      'wire_prompt_sha256': sha(wire.encode()),
                                      'wire_prompt_bytes': len(wire.encode()), 'wire_prompt_characters': len(wire)}
            trusted = {key: value for key,value in row.items() if key != 'packet'}
            trusted.update(arm_rendering_sha256=arm_map, unique_renderings=unique,
                           selected_for_mini=row['packet_sha256'] in mini)
            packets.append(trusted);by_hash[row['packet_sha256']] = trusted
        # Full v2 primary first (including mini), then secondary; v1 last.
        for model_index, model in enumerate(MODELS):
            for row in ordered:
                info = by_hash[row['packet_sha256']]
                stage = ('mini' if row['packet_sha256'] in mini else 'primary') if cohort=='v2' and model_index==0 else 'secondary' if cohort=='v2' else 'archival'
                cells = []
                for digest, source in info['unique_renderings'].items():
                    arms = [arm for arm,value in info['arm_rendering_sha256'].items() if value==digest]
                    for repetition in [0,1]:
                        item = {key:info[key] for key in ['packet_id','packet_sha256','packet_path','cohort','source_task','episode_id','action_effect','tool_name']}
                        item.update(rendering_path=source['path'], rendering_sha256=digest, rendering_arms=arms,
                                    model=model, repetition=repetition, stage=stage)
                        item['item_id'] = item_identity(item,config)
                        cells.append(item)
                seed = int(sha(f'{SEED}:{cohort}:{row["packet_sha256"]}:{model}'.encode()),16)
                random.Random(seed).shuffle(cells)
                schedule.extend(cells)
        cohort_counts[cohort] = {'typed_packets':len(records),'excluded_text_only':excluded,
                                'source_tasks':sorted({r['source_task'] for r in records},key=int),
                                'source_episodes':len({r['episode_id'] for r in records}),
                                'effects':dict(Counter(r['action_effect'] for r in records))}
    if len({r['item_id'] for r in schedule}) != len(schedule):
        raise ValueError('duplicate planned item identity')
    if len(schedule)>config['max_attempts']:
        raise ValueError('schedule exceeds authorization')
    comparisons = {cohort:{contrast:sum(p['arm_rendering_sha256'][a]!=p['arm_rendering_sha256'][b] for p in packets if p['cohort']==cohort)
                          for contrast,(a,b) in {'K-C':('K','C'),'R-C':('R','C')}.items()} for cohort in ['v2','v1']}
    if not any(comparisons['v2'].values()):
        raise ValueError('All primary arms structurally identical; do not execute')
    manifest = {'schema_version':1, 'created_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
                'selection_uses_labels_or_outcomes':False,'scheduler_seed':SEED,
                'projection':{'retained_exact_top_level_fields':list(FIELDS),'removed_provenance_fields':sorted(REMOVED),
                              'nested_projection':'none; preserve every policy/schema/message/candidate value and functional identifier'},
                'cohorts':cohort_counts,'packets':packets,'consumed_source_sha256':sources,
                'distinct_contrast_packets':comparisons,'planned_unique_generations':len(schedule),
                'stage_counts':dict(Counter(r['stage'] for r in schedule)),
                'model_transport_fingerprints':{m:fingerprint(m) for m in MODELS}}
    write(directory/'manifest.json',manifest)
    write(directory/'schedule.json',{'phase':config['phase'],'items':schedule})
    write(ROOT/args.config,config)
    print(json.dumps({'config':args.config,'manifest':config['prepared_manifest_path'],'planned':len(schedule),
                      'stages':manifest['stage_counts'],'cohorts':cohort_counts,'contrasts':comparisons},indent=2))


if __name__ == '__main__':main()
