"""Descriptive ablation analysis. Windows, not individual RPCs, are repeats."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import statistics


def save_csv(path, rows):
    with path.open('w', newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    args=parser.parse_args()
    base=args.directory.resolve()
    decision=base/'decision-results'
    costs=list(csv.DictReader((decision/'cost-model.csv').open()))
    summaries=[]
    for endpoints in ['false','true']:
        for context in ['false','true']:
            selected=[r for r in costs if r['endpoints']==endpoints and r['context_table']==context]
            regrets=[float(r['reference_regret_frac']) for r in selected]
            errors=[float(r['estimated_bottleneck_ms'])/float(r['reference_evaluated_bottleneck_ms'])-1 for r in selected]
            summaries.append(dict(endpoints=endpoints,context_table=context,cases=len(selected),
                                  median_reference_regret_pct=100*statistics.median(regrets),
                                  maximum_reference_regret_pct=100*max(regrets),
                                  changed_split_cases=sum(r['chosen_split']!=r['oracle_split'] for r in selected),
                                  median_reference_prediction_error_pct=100*statistics.median(errors)))
    save_csv(decision/'cost-model-aggregate.csv',summaries)

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(7,4))
    labels={('true','true'):'Full reference',('false','true'):'No endpoint terms',
            ('true','false'):'Frozen context 128',('false','false'):'Both removed'}
    for endpoints,context in [('true','true'),('false','true'),('true','false'),('false','false')]:
        selected=[r for r in costs if r['endpoints']==endpoints and r['context_table']==context and r['speed_b']=='1' and r['link_ms']=='0.5']
        selected.sort(key=lambda r:int(r['context']))
        ax.plot([int(r['context']) for r in selected],[100*float(r['reference_regret_frac']) for r in selected],marker='o',label=labels[(endpoints,context)])
    ax.set_xlabel('Context tokens');ax.set_ylabel('Reference-model bottleneck increase (%)')
    ax.set_title('Separated cost-model ablations — analytical, not runtime gains')
    ax.grid(alpha=.2);ax.legend();fig.tight_layout()
    for suffix in ['png','svg','pdf']:fig.savefig(base/f'cost-model-ablation.{suffix}',dpi=180)
    plt.close(fig)

    policy=list(csv.DictReader((decision/'policy.csv').open()))
    fig,ax=plt.subplots(figsize=(7,4))
    for margin,label in [('0','Zero margin'),('0.13','13% safety margin')]:
        selected=[r for r in policy if r['policy']=='gate' and r['transition_model']=='full-chain' and r['speed_b']=='0.7' and r['link_ms']=='0.5' and r['horizon_s']=='30' and r['margin']==margin]
        selected.sort(key=lambda r:int(r['context']))
        ax.plot([int(r['context']) for r in selected],[float(r['margin_acceptance_boundary_s']) for r in selected],marker='o',label=label)
    ax.axhline(30,color='gray',linestyle='--',label='Default 30 s horizon')
    ax.set_xlabel('Context tokens');ax.set_ylabel('Model-derived acceptance horizon (s)')
    ax.set_title('Transition gate sensitivity — no measured crossover')
    ax.grid(alpha=.2);ax.legend()
    fig.text(.5,.015,'Gate inequality only; the separate 15% improvement threshold and cooldown still apply.',ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.06,1,1))
    for suffix in ['png','svg','pdf']:fig.savefig(base/f'gate-horizon-sensitivity.{suffix}',dpi=180)
    plt.close(fig)

    queue=base/'queue-results'
    if not (queue/'windows.json').exists():
        print('Decision analysis saved; queue data not yet present')
        return
    windows=json.loads((queue/'windows.json').read_text())
    queue_meta=json.loads((queue/'metadata.json').read_text())
    if len(windows)!=len(queue_meta['schedule']):
        print(f"Queue matrix incomplete: {len(windows)}/{len(queue_meta['schedule'])}; no final queue analysis written")
        return
    groups=defaultdict(list)
    for row in windows:groups[(row['service_ms'],row['concurrency'],row['mode'])].append(row)
    aggregated=[]
    for (service,q,mode),rows in sorted(groups.items()):
        result=dict(service_ms=service,concurrency=q,mode=mode,windows=len(rows),
                    requests=sum(r['requests'] for r in rows),failures=sum(r['failures'] for r in rows))
        for field in ['completed_rpcs_per_s','mean_rpc_ms','mean_compute_ms',
                      'mean_server_lock_wait_ms','mean_residual_ms','mean_queue_corrected_residual_ms',
                      'mean_client_admission_wait_ms','mean_client_completion_ms']:
            values=[r[field] for r in rows]
            result[field]=statistics.mean(values)
            result[field+'_min']=min(values);result[field+'_max']=max(values)
        result['queue_fraction_of_mean_residual']=result['mean_server_lock_wait_ms']/result['mean_residual_ms']
        aggregated.append(result)
    save_csv(queue/'aggregate.csv',aggregated)
    (queue/'aggregate.json').write_text(json.dumps(aggregated,indent=2)+'\n')
    paired=[]
    for service in [5,20,50]:
        for q in [1,2,4]:
            diffs=[]
            for repeat in [1,2,3]:
                direct=next((r for r in windows if r['service_ms']==service and r['concurrency']==q and r['mode']=='direct' and r['repeat']==repeat),None)
                admitted=next((r for r in windows if r['service_ms']==service and r['concurrency']==q and r['mode']=='admitted' and r['repeat']==repeat),None)
                if direct and admitted:diffs.append(direct['mean_residual_ms']-admitted['mean_residual_ms'])
            if diffs:paired.append(dict(service_ms=service,concurrency=q,paired_windows=len(diffs),mean_residual_difference_ms=statistics.mean(diffs),min_difference_ms=min(diffs),max_difference_ms=max(diffs)))
    if paired:save_csv(queue/'paired-descriptive.csv',paired)
    fig,axes=plt.subplots(1,3,figsize=(12,4),sharey=False)
    for service,ax in zip([5,20,50],axes):
        for mode,field,label,color in [('direct','mean_residual_ms','Direct: RPC − compute','#2463ab'),('direct','mean_queue_corrected_residual_ms','Direct: also subtract lock wait','#378150'),('admitted','mean_residual_ms','FIFO admission: RPC − compute','#be5b22')]:
            selected=sorted((r for r in aggregated if r['service_ms']==service and r['mode']==mode),key=lambda r:r['concurrency'])
            means=[r[field] for r in selected]
            ax.errorbar([r['concurrency'] for r in selected],means,yerr=[[m-r[field+'_min'] for m,r in zip(means,selected)],[r[field+'_max']-m for m,r in zip(means,selected)]],marker='o',capsize=3,label=label,color=color)
        ax.set_title(f'{service} ms simulated service')
        ax.set_xlabel('Concurrent closed-loop clients');ax.set_xticks([1,2,4]);ax.grid(alpha=.2)
    axes[0].set_ylabel('Mean residual per RPC (ms)');axes[-1].legend(fontsize=7)
    fig.suptitle('Queue contamination pilot — instrumented simulation over loopback')
    fig.text(.5,.015,f"{queue_meta['repeats']} windows per condition; bars show observed window range, not confidence intervals. No real model or eBPF.",ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.07,1,.92))
    for suffix in ['png','svg','pdf']:fig.savefig(base/f'queue-contamination.{suffix}',dpi=180)
    plt.close(fig)
    print(json.dumps(dict(cost_model_rows=len(costs),policy_rows=len(policy),queue_windows=len(windows),queue_requests=sum(r['requests'] for r in windows),failures=sum(r['failures'] for r in windows))))

    calibration=base/'calibration-results'
    if (calibration/'windows.json').exists():
        cal=json.loads((calibration/'windows.json').read_text())
        cal_meta=json.loads((calibration/'metadata.json').read_text())
        if len(cal)!=len(cal_meta['schedule']):
            print('Calibration incomplete; final calibration analysis skipped')
            return
        comparison=[]
        for service in [5,50]:
            for q in [1,4]:
                pairs=[]
                for repeat in [1,2,3]:
                    off=next(r for r in cal if r['service_ms']==service and r['concurrency']==q and not r['instrumented'] and r['repeat']==repeat)
                    on=next(r for r in cal if r['service_ms']==service and r['concurrency']==q and r['instrumented'] and r['repeat']==repeat)
                    pairs.append(on['mean_residual_ms']-off['mean_residual_ms'])
                off=[r['mean_residual_ms'] for r in cal if r['service_ms']==service and r['concurrency']==q and not r['instrumented']]
                on=[r['mean_residual_ms'] for r in cal if r['service_ms']==service and r['concurrency']==q and r['instrumented']]
                comparison.append(dict(service_ms=service,concurrency=q,paired_windows=len(pairs),
                                       mean_original_residual_ms=statistics.mean(off),
                                       mean_instrumented_residual_ms=statistics.mean(on),
                                       mean_difference_ms=statistics.mean(pairs),min_difference_ms=min(pairs),max_difference_ms=max(pairs)))
        save_csv(calibration/'paired-overhead.csv',comparison)
        (calibration/'paired-overhead.json').write_text(json.dumps(comparison,indent=2)+'\n')
        fig,ax=plt.subplots(figsize=(7,4))
        means=[r['mean_difference_ms'] for r in comparison]
        ax.errorbar(range(4),means,yerr=[[m-r['min_difference_ms'] for m,r in zip(means,comparison)],
                                       [r['max_difference_ms']-m for m,r in zip(means,comparison)]],fmt='o',capsize=5)
        ax.axhline(0,color='gray',linestyle='--')
        ax.set_xticks(range(4),[f"{r['service_ms']} ms, Q={r['concurrency']}" for r in comparison])
        ax.set_ylabel('Wrapped − original mean residual (ms)')
        ax.set_title('Instrumentation calibration — synthetic loopback only')
        ax.grid(alpha=.2)
        fig.text(.5,.015,f"3 paired blocks; bars show observed paired-difference range, not confidence intervals. {cal_meta['window_s']:g} s windows.",ha='center',fontsize=8)
        fig.tight_layout(rect=(0,.06,1,1))
        for suffix in ['png','svg','pdf']:fig.savefig(base/f'instrumentation-calibration.{suffix}',dpi=180)
        plt.close(fig)
        print(json.dumps(dict(calibration_windows=len(cal),calibration_requests=sum(r['requests'] for r in cal),calibration_failures=sum(r['failures'] for r in cal))))


if __name__=='__main__':main()
