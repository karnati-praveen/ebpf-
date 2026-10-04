"""Descriptive summaries for the synthetic local runtime probe; no significance claim."""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
import statistics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    rows = json.loads((directory / 'runtime-probe-summary.json').read_text())
    groups = defaultdict(list)
    requests = defaultdict(list)
    for line in (directory / 'runtime-probe-requests.jsonl').read_text().splitlines():
        request = json.loads(line)
        if request['ok']:
            requests[(request['mode'], request['workers'], request['concurrency'])].append(request)
    for row in rows:
        groups[(row['mode'], row['workers'], row['concurrency'])].append(row)
    summaries = []
    for (mode, workers, concurrency), runs in sorted(groups.items()):
        rates = [r['completed_tokens_per_s_full_observation'] for r in runs]
        summary = dict(
            mode=mode, workers=workers, concurrency=concurrency,
            windows=len(runs), requests=sum(r['requests'] for r in runs),
            failures=sum(r['failures'] for r in runs),
            mean_tokens_per_s=statistics.mean(rates),
            min_tokens_per_s=min(rates), max_tokens_per_s=max(rates),
            mean_window_median_ttft_ms=statistics.mean(r['median_ttft_ms'] for r in runs),
            mean_window_p95_ttft_ms=statistics.mean(r['p95_ttft_ms'] for r in runs),
            mean_window_median_completion_ms=statistics.mean(r['median_completion_ms'] for r in runs),
        )
        raw = requests[(mode, workers, concurrency)]
        clients = sorted(r['client_completion_ms'] for r in raw if 'client_completion_ms' in r)
        waits = [r['routing_wait_ms'] for r in raw if 'routing_wait_ms' in r]
        summary['pooled_median_client_completion_ms'] = statistics.median(clients) if clients else None
        summary['pooled_p95_client_completion_ms'] = clients[int((len(clients)-1)*.95)] if clients else None
        summary['max_routing_wait_ms'] = max(waits) if waits else None
        summaries.append(summary)
    (directory / 'aggregate.json').write_text(json.dumps(summaries, indent=2) + '\n')
    with (directory / 'aggregate.csv').open('w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    worker_counts = sorted({s['workers'] for s in summaries})
    fig, axes = plt.subplots(1, len(worker_counts), figsize=(4.2 * len(worker_counts), 4.2), squeeze=False)
    for workers, ax in zip(worker_counts, axes[0]):
        for mode, color in [('pipeline', '#2463ab'), ('replicas', '#be5b22')]:
            items = sorted((s for s in summaries if s['workers'] == workers and s['mode'] == mode), key=lambda s: s['concurrency'])
            if not items:
                continue
            means = [s['mean_tokens_per_s'] for s in items]
            errors = [[m - s['min_tokens_per_s'] for m, s in zip(means, items)],
                      [s['max_tokens_per_s'] - m for m, s in zip(means, items)]]
            ax.errorbar([s['concurrency'] for s in items], means, yerr=errors,
                        marker='o', capsize=4, color=color, label=mode)
        ax.set_title(f'{workers} simulated worker(s)')
        ax.set_xlabel('Concurrent closed-loop clients')
        ax.set_xticks(sorted({s['concurrency'] for s in summaries}))
        ax.set_ylim(bottom=0)
        ax.grid(alpha=.2)
        ax.legend()
    axes[0][0].set_ylabel('Completed tokens / second (including drain)')
    fig.suptitle('Synthetic local loopback probe — no real model or physical cluster', fontsize=12)
    meta = json.loads((directory / 'runtime-probe-meta.json').read_text())
    policy = meta.get('replica_policy', 'per-client cyclic')
    fig.text(.5, .015, f'Replica routing: {policy}. Error bars: observed run range; not confidence intervals.', ha='center', fontsize=8)
    fig.tight_layout(rect=(0, .07, 1, .91))
    fig.savefig(directory / 'throughput.png', dpi=160)
    fig.savefig(directory / 'throughput.svg')
    plt.close(fig)
    print(json.dumps({'windows': len(rows), 'requests': sum(r['requests'] for r in rows),
                      'failures': sum(r['failures'] for r in rows), 'groups': len(summaries)}))


if __name__ == '__main__':
    main()
