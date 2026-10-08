#!/usr/bin/env python3
"""Plot observed single-repetition local results; no uncertainty is inferred."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
rows=[json.loads(line) for line in (ROOT/'results/validation-2026-10-08/baseline-functional/runs.jsonl').read_text().splitlines()]
styles=[('unsplit-1t','Unsplit, 1 thread','#757575','o'),('unsplit-2t','Unsplit, 2 threads','#d95f02','s'),('replicas-2x1t','Two replicas, 1 thread each','#1b9e77','^'),('pipeline-2x1t','Pipeline, 1 thread per stage','#355caa','D')]
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'pdf.fonttype':42,'ps.fonttype':42})
fig,axes=plt.subplots(1,2,figsize=(7.0,2.45),sharey=True)
for ax,context in zip(axes,(32,128)):
 for mode,label,color,marker in styles:
  selected=sorted((r for r in rows if r['mode']==mode and r['context']==context),key=lambda r:r['concurrency'])
  assert len(selected)==4 and all(r['failures']==0 for r in selected)
  ax.plot([r['concurrency'] for r in selected],[r['whole_run_tps'] for r in selected],label=label,color=color,marker=marker,linewidth=1.2,markersize=4)
 ax.set_xticks((1,2,4,8));ax.set_xlabel('Concurrent requests');ax.set_title(f'{context} input tokens');ax.grid(axis='y',alpha=.25)
axes[0].set_ylabel('Whole-run output tokens/s')
handles,labels=axes[0].get_legend_handles_labels()
fig.legend(handles,labels,loc='lower center',ncol=2,frameon=False,bbox_to_anchor=(.5,-.02))
fig.tight_layout(rect=(0,.15,1,1))
fig.savefig(ROOT/'docs/publication/figures/local-baselines.pdf',bbox_inches='tight')
fig.savefig(ROOT/'docs/publication/figures/local-baselines.png',dpi=220,bbox_inches='tight')
print('Saved observed local baseline figure (one repetition per condition).')
