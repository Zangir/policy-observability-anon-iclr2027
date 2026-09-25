"""Descriptive fixed-cohort analysis; preserves all planned cells and failures."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import statistics
from decision_screen.render import ROOT, strict_json, sha
from adapter.decision_screen_transport import parse_response, make_payload, make_prompt

DECISIONS = ('ALLOW','BLOCK','ASK')
CONTRASTS = {'K-C':('K','C'), 'R-C':('R','C')}


def mean(values):
    return statistics.mean(values) if values else None


def pair_statistics(a, b):
    if len(a)!=2 or len(b)!=2 or any(x not in DECISIONS for x in a+b):
        raise ValueError('two valid independent repetitions required per arm')
    cross = sum(x!=y for x in a for y in b)/4
    within = ((a[0]!=a[1])+(b[0]!=b[1]))/2
    return {'cross_disagreement':cross,'within_disagreement':within,'excess_disagreement':cross-within}


def normalize(config, schedule, registry):
    rows=[];usage=[];generation_ids=set();checks=0
    state = registry.get('items',{})
    if set(state)!={item['item_id'] for item in schedule}:
        raise ValueError('registry/schedule item set differs')
    for item in schedule:
        saved=state[item['item_id']]
        if saved['item']!=item:
            raise ValueError('saved planned item changed')
        status=saved['status'];decision=None;generation=saved.get('generation_id');meta=None
        if generation:
            if generation in generation_ids:raise ValueError('generation reused across independent items')
            generation_ids.add(generation)
        if status in {'completed','failed'}:
            run=ROOT/config['output_root']/'calls'/generation
            raw=(run/'metadata.json').read_bytes()
            if sha(raw)!=saved['metadata_sha256']:raise ValueError('terminal metadata hash changed')
            meta=strict_json(raw)
            if any(meta.get(k)!=item[k] for k in ['item_id','packet_sha256','rendering_sha256','repetition']):
                raise ValueError('terminal item lineage differs')
            if meta['requested_model']!=item['model'] or meta['generation_id']!=generation or meta['status']!=status:
                raise ValueError('terminal model/generation/status differs')
            if meta['release_sha256']!=registry['release_sha256']:
                raise ValueError('release lineage differs')
            for name,digest in meta['artifact_sha256'].items():
                if Path(name).name!=name or sha((run/name).read_bytes())!=digest:
                    raise ValueError('raw artifact changed')
                checks+=1
            evidence=(ROOT/item['rendering_path']).read_text()
            prompt=make_prompt(make_payload(evidence,config['guard_instruction']))
            if (run/'prompt.txt').read_text()!=prompt:
                raise ValueError('actual prompt differs from planned rendering/contract')
            if status=='completed':
                parsed,events=parse_response(run, message_count=len(strict_json(evidence)['actor_visible_messages']))
                if parsed!=meta['decision'] or parsed!=saved['decision']:
                    raise ValueError('saved decision differs from raw response')
                decision=parsed['decision']
            else:
                status=meta['category']
                if status in {'completed','valid_decision'}:raise ValueError('failure has success category')
            usage.append({'item_id':item['item_id'],'generation_id':generation,
                          'cohort':item['cohort'],'model':item['model'],
                          'elapsed_seconds':meta.get('elapsed_seconds'),
                          'termination_reason':meta.get('termination_reason'),'exit_status':meta.get('exit_status'),
                          'backend_reported_usage':meta.get('exposed_usage'),
                          'observed_model':meta.get('observed_model'),
                          'requested_model':meta['requested_model'],
                          'prompt_bytes':len(prompt.encode()),'prompt_characters':len(prompt),
                          'rendered_bytes':len(evidence.encode()),'rendered_characters':len(evidence)})
        elif status=='planned':
            status='not_run' if registry.get('phase_closed') else 'planned'
        for arm in item['rendering_arms']:
            rows.append({key:item[key] for key in ['packet_id','packet_sha256','cohort','source_task','episode_id','action_effect','tool_name','model','item_id']} |
                        {'rendering':arm,'rep':item['repetition'],'status':status,'decision':decision,
                         'generation_id':generation,'shared_generation':len(item['rendering_arms'])>1,
                         'unique_rendering_sha256':item['rendering_sha256']})
    if len(generation_ids)!=registry['attempts']:
        raise ValueError('attempt counter differs from unique generation IDs')
    return rows,usage,checks


def summaries(rows):
    distributions=[];groups=defaultdict(list)
    for row in rows:
        for scope,stratum in [('cohort','all'),('task',row['source_task']),('action_effect',row['action_effect'])]:
            groups[(row['cohort'],row['model'],scope,stratum,row['rendering'])].append(row)
    for (cohort,model,scope,stratum,arm),values in sorted(groups.items()):
        categories=Counter(r['decision'] if r['decision'] is not None else r['status'] for r in values)
        valid=sum(categories[d] for d in DECISIONS);total=len(values)
        distributions.append({'cohort':cohort,'model':model,'scope':scope,'stratum':stratum,'rendering':arm,
            'planned_cells':total,'valid_decisions':valid,'categories':dict(categories),
            'fractions_all_planned':{k:v/total for k,v in categories.items()},
            'decision_rates_among_valid':{d:categories[d]/valid if valid else None for d in DECISIONS},
            'source_tasks':len({r['source_task'] for r in values}),
            'source_episodes':len({r['episode_id'] for r in values}),
            'candidates':len({r['packet_sha256'] for r in values})})
    by_packet=defaultdict(dict)
    for row in rows:
        key=(row['cohort'],row['model'],row['packet_sha256'])
        cell=(row['rendering'],row['rep'])
        if cell in by_packet[key]:raise ValueError('duplicate analysis arm/repetition')
        by_packet[key][cell]=row
    packet_results=[];tables=defaultdict(Counter)
    for (cohort,model,packet),cells in sorted(by_packet.items()):
        info=next(iter(cells.values()))
        for contrast,(a,b) in CONTRASTS.items():
            aa=[cells.get((a,r)) for r in [0,1]];bb=[cells.get((b,r)) for r in [0,1]]
            if any(r is None for r in aa+bb):raise ValueError('missing planned arm/repetition row')
            structural=aa[0]['unique_rendering_sha256']==bb[0]['unique_rendering_sha256']
            valid=not structural and all(r['decision'] in DECISIONS for r in aa+bb)
            rec={key:info[key] for key in ['cohort','model','packet_id','packet_sha256','source_task','episode_id','action_effect']}
            rec.update(contrast=contrast,structurally_unavailable=structural,complete_valid=valid,
                       statuses={f'{arm}{r}':cells[(arm,r)]['status'] for arm in [a,b] for r in [0,1]})
            if valid:rec.update(pair_statistics([r['decision'] for r in aa],[r['decision'] for r in bb]))
            packet_results.append(rec)
            if structural:continue
            for scope,stratum in [('cohort','all'),('task',info['source_task']),('action_effect',info['action_effect'])]:
                for repetition in [0,1]:
                    x,y=aa[repetition],bb[repetition]
                    key=(cohort,model,contrast,scope,stratum,'repetition_matched_operational')
                    tables[key][(x['decision'] or 'NO_VALID_DECISION',y['decision'] or 'NO_VALID_DECISION')]+=1
                    if x['decision'] and y['decision']:
                        tables[(cohort,model,contrast,scope,stratum,'repetition_matched_valid')][(x['decision'],y['decision'])]+=1
                if valid:
                    for x in aa:
                        for y in bb:
                            tables[(cohort,model,contrast,scope,stratum,'four_cross_pairs_complete_valid')][(x['decision'],y['decision'])]+=1
    aggregate=[];metrics=defaultdict(list)
    for rec in packet_results:
        for scope,stratum in [('cohort','all'),('task',rec['source_task']),('action_effect',rec['action_effect'])]:
            metrics[(rec['cohort'],rec['model'],rec['contrast'],scope,stratum)].append(rec)
    for (cohort,model,contrast,scope,stratum),values in sorted(metrics.items()):
        valid=[v for v in values if v['complete_valid']]
        expected_tasks=sorted({v['source_task'] for v in values},key=int)
        observed_tasks=sorted({v['source_task'] for v in valid},key=int)
        item={'cohort':cohort,'model':model,'contrast':contrast,'scope':scope,'stratum':stratum,
              'planned_candidates':len(values),'structurally_unavailable':sum(v['structurally_unavailable'] for v in values),
              'complete_valid_candidates':len(valid),'incomplete_or_failed_candidates':sum(not v['complete_valid'] and not v['structurally_unavailable'] for v in values),
              'expected_source_tasks':expected_tasks,'complete_valid_source_tasks':observed_tasks,
              'source_episodes':len({v['episode_id'] for v in values})}
        for metric in ['cross_disagreement','within_disagreement','excess_disagreement']:
            item[metric+'_packet_weighted']=mean([v[metric] for v in valid])
            task_means=[mean([v[metric] for v in valid if v['source_task']==task]) for task in observed_tasks]
            item[metric+'_task_macro']=mean(task_means)
        aggregate.append(item)
    contingencies=[]
    for (cohort,model,contrast,scope,stratum,kind),counts in sorted(tables.items()):
        labels=list(DECISIONS)+(['NO_VALID_DECISION'] if kind.endswith('operational') else [])
        contingencies.append({'cohort':cohort,'model':model,'contrast':contrast,'scope':scope,'stratum':stratum,'pairing':kind,
                              'pairs':sum(counts.values()),'cells':[{'a':a,'b':b,'count':counts[(a,b)]} for a in labels for b in labels]})
    return {'distributions':distributions,'packet_contrasts':packet_results,'contrast_summaries':aggregate,'contingencies':contingencies}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',default='configs/decision_screen_20260919.json')
    parser.add_argument('--output',required=True)
    args=parser.parse_args();out=ROOT/args.output
    if out.exists():raise ValueError('analysis output must be new; preserve prior checkpoints')
    config=strict_json((ROOT/args.config).read_bytes())
    schedule=strict_json((ROOT/config['schedule_path']).read_bytes())['items']
    registry_path=ROOT/config['output_root']/'registry.json'
    registry_raw=registry_path.read_bytes();registry=strict_json(registry_raw)
    rows,usage,checks=normalize(config,schedule,registry)
    result=summaries(rows)
    item_counts=Counter(r['status'] for r in registry['items'].values())
    result.update(schema_version=1,generated_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
        registry_sha256=sha(registry_raw),phase_closed=registry.get('phase_closed',False),
        source_sha256=sha(Path(__file__).read_bytes()),unique_planned_generations=len(schedule),
        attempted_generations=registry['attempts'],unique_item_statuses=dict(item_counts),
        attempt_count_scope='Conservative reservations; an interrupted prelaunch reservation may not have reached the provider.',
        subprocess_terminal_records=len(usage),
        subprocess_launch_errors=sum(u['termination_reason']=='launch_error' for u in usage),
        reservations_without_terminal_metadata=registry['attempts']-len(usage),
        logical_arm_repetition_rows=len(rows),raw_artifact_checks=checks,
        human_label_count=0,human_correctness_status='Decision improvement is unresolved unless a separately validated genuine-human join establishes subset-specific evidence.',
        interpretation='Finite-cohort descriptive serialization sensitivity/noise; no population inference, ranking, permission gold or prevented historical actions.')
    out.mkdir(parents=True)
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'normalized_rows.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in rows))
    (out/'usage.json').write_text(json.dumps(usage,indent=2)+'\n')
    fields=['cohort','model','contrast','scope','stratum','planned_candidates','structurally_unavailable','complete_valid_candidates','incomplete_or_failed_candidates','expected_source_tasks','complete_valid_source_tasks','source_episodes']+[m+'_'+w for m in ['cross_disagreement','within_disagreement','excess_disagreement'] for w in ['packet_weighted','task_macro']]
    with (out/'contrast_summary.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(result['contrast_summaries'])
    with (out/'decision_distributions.csv').open('w') as f:
        fields=['cohort','model','scope','stratum','rendering','planned_cells','valid_decisions','source_tasks','source_episodes','candidates','categories','fractions_all_planned','decision_rates_among_valid']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for r in result['distributions']:
            writer.writerow({k:json.dumps(v,sort_keys=True) if isinstance(v,dict) else v for k,v in r.items()})
    print(json.dumps({k:result[k] for k in ['unique_planned_generations','attempted_generations','unique_item_statuses','raw_artifact_checks','phase_closed']},indent=2))


if __name__=='__main__':main()
