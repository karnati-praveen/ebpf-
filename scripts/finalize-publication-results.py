#!/usr/bin/env python3
"""Insert only completed, audited campaigns into the IEEE writing manuscript."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import statistics as st
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'bench'))
from publication_analyze import analyze, percentile


def load(directory):
    report = analyze(directory)
    if report['completed_runs'] != report['expected_runs'] or report['missing_runs']:
        raise RuntimeError(f'incomplete campaign: {directory}')
    status = json.loads((directory/'completion-status.json').read_text())
    if not status['complete']:
        raise RuntimeError(f'campaign driver did not record completion: {directory}')
    return report, json.loads((directory/'manifest.json').read_text()), [json.loads(x) for x in (directory/'runs.jsonl').read_text().splitlines()]


def ratio_interval(a, b):
    rng = random.Random(20261007)
    ratios = [st.mean(rng.choices(a, k=len(a)))/st.mean(rng.choices(b, k=len(b))) for _ in range(10000)]
    return st.mean(a)/st.mean(b), [percentile(ratios, .025), percentile(ratios, .975)]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--main', type=Path, default=ROOT/'results/publication-2026-10-07/main')
    ap.add_argument('--engine', type=Path, default=ROOT/'results/publication-2026-10-07/optimized-epyc7763')
    ap.add_argument('--multistage', type=Path, default=ROOT/'results/publication-2026-10-07/multistage-epyc7763')
    args = ap.parse_args()
    report, manifest, runs = load(args.main)
    engine, em, eruns = load(args.engine)
    multi, mm, mruns = load(args.multistage)
    if manifest['cpu'] != em['cpu'] or manifest['cpu'] != mm['cpu'] or em['source_manifest_sha256'] != hashlib.sha256((args.main/'manifest.json').read_bytes()).hexdigest():
        raise RuntimeError('campaign hardware or source provenance mismatch')
    for name, digest in manifest['source_sha256'].items():
        snapshot = args.main/'source-snapshot'/name
        if hashlib.sha256(snapshot.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f'source snapshot mismatch: {name}')
    summaries = {(r['mode'], r['context'], r['concurrency']):r for r in report['summaries']}
    conditions = sorted({(r['context'], r['concurrency']) for r in report['summaries']})
    lines = [f"The completed runtime matrix contains {report['completed_runs']} runs and {report['total_requests']} requests, with {report['failures']} failed or reference-mismatched requests. Each arm/condition has ten restart-block observations. Table \\ref{{tab:local}} reports run medians; uncertainty appears in Fig. \\ref{{fig:local}} and in the paired contrasts in the artifact.", '',
        r'\begin{table}[t]', r'\centering\small',
        r'\caption{Single-host runtime throughput medians (tokens/s), ten runs per cell. U1/U2: unsplit with one/two threads; R2: two whole-model replicas; P2: fixed two-stage pipeline. Q is concurrent requests. All arms use the same FP32 backend and token reference.}',
        r'\begin{tabular}{rrrrrr}', r'\toprule Context & Q & U1 & U2 & R2 & P2\\', r'\midrule']
    for c, q in conditions:
        values = [summaries[m,c,q]['median_tps'] for m in ('unsplit-1t','unsplit-2t','replicas-2x1t','pipeline-2x1t')]
        lines.append(f'{c} & {q} & '+ ' & '.join(f'{v:.3f}' for v in values) + r'\\')
    lines += [r'\bottomrule', r'\end{tabular}', r'\label{tab:local}', r'\end{table}', '',
        r'\begin{figure*}[t]', r'\centering', r'\includegraphics[width=.95\textwidth]{figures/local-baselines.pdf}',
        r'\caption{Completed local runtime matrix. Points are run-level mean throughput, error bars descriptive 95\% percentile block-bootstrap intervals (10,000 resamples). Requests within a run are not repetitions. Context refers to seeded token inputs, output length is 16.}', r'\label{fig:local}', r'\end{figure*}', '']
    contrasts = [r for r in report['contrasts'] if r['baseline']=='replicas-2x1t']
    lines += ['Against the first-available replicas, the pipeline\'s paired mean throughput changes range from '+f"{min(r['paired_mean_tps_change_pct'] for r in contrasts):.1f}\\% to {max(r['paired_mean_tps_change_pct'] for r in contrasts):.1f}\\%. The individual intervals and failures are retained rather than interpreting the range as a significance or equivalence test.", '']
    diagnostic = [summaries['pipeline-2x1t', c, q] for c,q in conditions if q>1]
    fractions = [r['decode_queue_fraction_of_residual'] for r in diagnostic]
    lines += [f"On real-model pipeline decode calls at concurrency above one, compute-lock wait accounts for {100*min(fractions):.1f}--{100*max(fractions):.1f}\\% of the summed call-minus-compute residual, depending on context and concurrency. These are ratios of summed durations within each condition; they are not network RTT or independent request-level confidence intervals. The experiment establishes contamination on actual gRPC model execution. It does not establish that queue-corrected telemetry improves placement or serving.", '',
        f"A separate optimized-engine campaign contains {engine['completed_runs']} runs and {engine['total_requests']} requests. It uses llama.cpp commit \\texttt{{{em['engine_commit'][:12]}}}, F32 weights converted from the same pinned checkpoint, F32 KV cache, two compute threads and eight continuous-batching slots. It records {engine['failures']} failed/invalid-length requests and {engine['reference_mismatches']} full-length outputs differing from the Hugging Face reference. This campaign follows the runtime matrix on the same host; it is not temporally paired or an isolated algorithm ablation.", '',
        r'\begin{table}[t]', r'\centering\small',
        r'\caption{Separately timed F32 optimized-engine throughput. Ratio is engine mean / pipeline mean; intervals independently resample the two campaigns, without controlling time-of-campaign effects.}',
        r'\begin{tabular}{rrrr}', r'\toprule Context & Q & Engine TPS & Ratio [95\%]\\',r'\midrule']
    comparison=[]
    for c,q in conditions:
        a=[r['whole_run_tps'] for r in eruns if r['context']==c and r['concurrency']==q]
        b=[r['whole_run_tps'] for r in runs if r['mode']=='pipeline-2x1t' and r['context']==c and r['concurrency']==q]
        ratio, interval=ratio_interval(a,b)
        comparison.append({'context':c,'concurrency':q,'engine_mean_tps':st.mean(a),'pipeline_mean_tps':st.mean(b),'engine_to_pipeline_mean_ratio':ratio,'independent_ratio_ci95':interval,'scope':'separate campaigns; temporal confounding not removed; implementation and batching differ'})
        lines.append(f'{c} & {q} & {st.mean(a):.3f} & {ratio:.2f} [{interval[0]:.2f}, {interval[1]:.2f}]'+r'\\')
    lines += [r'\bottomrule',r'\end{tabular}',r'\label{tab:engine}',r'\end{table}', '',
        'The optimized implementation changes batching, compute kernels and the HTTP path. Its measured throughput is a deployment alternative, not evidence that a particular controller change causes the difference. The same precision and compute-thread budget do not make the two software paths identical.', '']
    lines += [f"A separate three-worker follow-up contains {multi['completed_runs']} runs and {multi['total_requests']} requests, with {multi['failures']} failures or token-reference mismatches. It uses a three-CPU compute budget, a 256-token input context and 32 output tokens. Three-thread unsplit serving and three first-available whole-model replicas are compared with fixed bottleneck and model-capacity layouts, selected using a separate five-sample component profile. The configured link coefficient is 1 ms; it is not a measured WAN coefficient. Conditions sharing a layout share a restart; repetition indices are the analysis blocks.", '',
        r'\begin{table}[t]',r'\centering\small',
        r'\caption{Three-worker throughput medians (tokens/s), ten runs per cell. U3: unsplit three threads; R3: three replicas; B3: bottleneck-model placement; C3: finite-concurrency-envelope placement. Empty stages leave CPUs unused.}',
        r'\begin{tabular}{rrrrr}',r'\toprule Q & U3 & R3 & B3 & C3\\',r'\midrule']
    ms={(r['mode'],r['concurrency']):r for r in multi['summaries']}
    for q in (1,2,4,8):
        values=[ms[m,q]['median_tps'] for m in ('unsplit-3t','replicas-3x1t','bottleneck-3x1t','capacity-3x1t')]
        lines.append(str(q)+' & '+' & '.join(f'{v:.3f}' for v in values)+r'\\')
    lines += [r'\bottomrule',r'\end{tabular}',r'\label{tab:multi}',r'\end{table}', '',
        'This follow-up adds real-model execution with more workers and longer inputs/outputs. Workers remain processes on one host; it does not establish physical heterogeneity or adaptive-controller superiority. The cost-model guarantee and runtime comparison remain separate claims.', '']
    text='\n'.join(lines)
    path=ROOT/'docs/publication/ieee-manuscript.md'
    manuscript=path.read_text()
    marker='<!-- LOCAL_RESULTS: populated only after the measured matrix and audit finish. -->'
    start='<!-- LOCAL_RESULTS_START -->'
    end='<!-- LOCAL_RESULTS_END -->'
    if marker in manuscript:
        manuscript=manuscript.replace(marker,start+'\n'+text+'\n'+end)
    elif start in manuscript and end in manuscript:
        before=manuscript.split(start)[0]
        after=manuscript.split(end)[1]
        manuscript=before+start+'\n'+text+'\n'+end+after
    else:
        raise RuntimeError('local-results insertion boundary absent')
    manuscript=manuscript.replace('but an optimized external engine remains unevaluated.',
        'and a separately timed F32 optimized engine supplies a practical alternative.')
    manuscript=manuscript.replace('an optimized external serving baseline,\nadditional models,',
        'temporally interleaved optimized-engine comparisons,\nadditional models,')
    cpu_start='The completed campaign uses an AMD EPYC 9V74 host with four visible CPUs.'
    cpu_end='are supplemental and are not pooled with the new campaign.'
    if cpu_start in manuscript:
        before,remaining=manuscript.split(cpu_start,1)
        _,after=remaining.split(cpu_end,1)
        manuscript=before+f"The primary campaign records {manifest['cpu']} with four visible CPUs. Workspace restarts required checkpoint resumes. Only matching CPU models, package versions and serving sources could resume a campaign. Different-CPU campaigns and pilots remain separate supplemental observations. Physical host identity was not retained across restarts, so measurements describe the recorded virtual CPU configuration rather than a guaranteed continuously allocated physical host."+after
    path.write_text(manuscript)
    out=ROOT/'results/publication-2026-10-07'
    (out/'engine-comparison.json').write_text(json.dumps(comparison,indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(7,2.6),sharey=True,layout='constrained')
    for ax,c in zip(axes,sorted({c for c,q in conditions})):
        for m,label in [('unsplit-1t','Unsplit, 1 thread'),('unsplit-2t','Unsplit, 2 threads'),('replicas-2x1t','Two replicas'),('pipeline-2x1t','Two-stage pipeline')]:
            rows=[summaries[m,c,q] for q in (1,2,4,8)]
            means=[r['mean_tps'] for r in rows]
            errors=[[v-r['mean_tps_ci95'][0] for v,r in zip(means,rows)], [r['mean_tps_ci95'][1]-v for v,r in zip(means,rows)]]
            ax.errorbar(range(4),means,yerr=errors,label=label,marker='o',markersize=3,linewidth=1,capsize=2)
        ax.set_xticks(range(4),[1,2,4,8]);ax.set_xlabel('Concurrent requests');ax.set_title(f'Context {c} tokens',fontsize=10);ax.grid(axis='y',alpha=.2)
    axes[0].set_ylabel('Whole-run tokens/s');axes[1].legend(fontsize=7,loc='best')
    figures=ROOT/'docs/publication/figures'
    figures.mkdir(exist_ok=True)
    fig.savefig(figures/'local-baselines.pdf');fig.savefig(figures/'local-baselines.png',dpi=200)
    print('Completed results inserted; figure and independent engine comparison generated')


if __name__=='__main__':
    main()
