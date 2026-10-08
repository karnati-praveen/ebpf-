#!/usr/bin/env python3
"""Run/block-level controller analysis; never pool campaigns or request samples."""
import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import statistics
from publication_analyze import bootstrap
from calibrated_campaign import checkpoint


def analyze(directory):
    manifest=json.loads((directory/'manifest.json').read_text())
    rows=checkpoint(directory/'runs.jsonl',[r['id'] for r in manifest['schedule']])
    groups=defaultdict(list);details=[]
    for row in rows:
        trial=directory/row['trial'];meta=json.loads((trial/'meta.json').read_text())
        with (trial/'requests.csv').open() as source:requests=list(csv.DictReader(source))
        migrations=json.loads((trial/'migrations.json').read_text())
        failures=sum(r['ok']!='1' for r in requests)
        forecast_errors=[100*(m['duration_ms']/m['predicted_ms']-1) for m in migrations
                         if m.get('status')=='complete' and m.get('predicted_ms',0)>0]
        item=dict(row,failures=failures,requests=len(requests),
                  median_client_completion_ms=statistics.median(float(r['duration_ms']) for r in requests) if requests else None,
                  maximum_internal_token_gap_ms=max((float(r.get('maximum_internal_token_gap_ms') or 0) for r in requests),default=0),
                  migration_observations=len(migrations),forecast_error_pct=forecast_errors,
                  contaminated=bool(meta['contaminated_by_unexpected_worker_restart']))
        details.append(item)
        key=tuple(row[k] for k in ('context','tokens','concurrency','demand','scenario'))
        groups[key].append(item)
    summaries=[];contrasts=[]
    for condition,items in sorted(groups.items()):
        by_arm=defaultdict(list)
        for item in items:by_arm[item['arm']].append(item)
        labels=dict(zip(('context','tokens','concurrency','demand','scenario'),condition))
        for arm,observations in sorted(by_arm.items()):
            valid=[r for r in observations if not r['contaminated']]
            values=[r['whole_run_tps'] for r in valid]
            summaries.append(dict(labels,arm=arm,attempted_runs=len(observations),valid_runs=len(valid),
                contaminated_runs=len(observations)-len(valid),failures=sum(r['failures'] for r in observations),
                mean_tps=statistics.mean(values) if values else None,mean_tps_ci95=bootstrap(values)))
        candidate={r['repetition']:r for r in by_arm.get('gate-calibrated',[]) if not r['contaminated']}
        for baseline in ('hysteresis','gate'):
            references={r['repetition']:r for r in by_arm.get(baseline,[]) if not r['contaminated']}
            paired=[(r,references[rep]) for rep,r in candidate.items() if rep in references]
            differences=[100*(r['whole_run_tps']/b['whole_run_tps']-1) for r,b in paired if b['whole_run_tps']>0]
            contrasts.append(dict(labels,baseline=baseline,paired_n=len(differences),
                mean_change_pct=statistics.mean(differences) if differences else None,ci95=bootstrap(differences),
                paired_failures=sum(r['failures']+b['failures'] for r,b in paired)))
    status=json.loads((directory/'completion-status.json').read_text())
    complete=status['complete'] and len(rows)==len(manifest['schedule'])
    result=dict(identity=manifest['identity'],phase=manifest['phase'],complete=complete,
                completed_runs=len(rows),expected_runs=len(manifest['schedule']),summaries=summaries,contrasts=contrasts,runs=details,
                analysis_unit='randomized restart block; paired by repetition within condition',
                uncertainty='10000-resample descriptive paired block bootstrap; unadjusted; no IID scenario assumption',
                timing_scope='final HTTP completion latency and internal token gaps; no streaming delivery measurement',
                inputs_sha256={name:hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in ('manifest.json','runs.jsonl','completion-status.json')})
    (directory/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
    lines=['# Calibrated-controller campaign', '',f"Completed {len(rows)}/{len(manifest['schedule'])} runs; complete={complete}.",
           '',result['analysis_unit']+'. '+result['timing_scope']+'.','',
           '| Arm | Context | Output | Q | Demand | Scenario | Runs | Mean TPS | Failures |',
           '|---|---:|---:|---:|---|---|---:|---:|---:|']
    for row in summaries:
        value='unavailable' if row['mean_tps'] is None else f"{row['mean_tps']:.3f}"
        lines.append(f"| {row['arm']} | {row['context']} | {row['tokens']} | {row['concurrency']} | {row['demand']} | {row['scenario']} | {row['valid_runs']} | {value} | {row['failures']} |")
    lines+=['','Incomplete reports are checkpoints. A completed run schedule alone does not demonstrate controller benefit.']
    (directory/'REPORT.md').write_text('\n'.join(lines)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    report=analyze(parser.parse_args().directory)
    print(f"{report['completed_runs']}/{report['expected_runs']} runs; complete={report['complete']}")
