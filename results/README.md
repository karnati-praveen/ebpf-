# Experiment results

Start here to find raw data, analysis, reports and logs by experiment.

Every result folder has a local guide: `README.md`, or `EXPERIMENT.md` when an
original README already exists. It names the experiment, original execution
environment and source, producing script, evidence type and folder contents.
Individual run guides include the saved policy, workload, repeat and IST start
time from `meta.json`. Unknown historical dates or paths are explicitly marked.

[Folder-by-folder index](folders.csv) maps every browsable folder to its guide.
[Experiment registry](experiments.json) records the source descriptions used
to generate them. Regenerate the guides and artifact catalog with:

```bash
python3 scripts/document-results.py
python3 scripts/index-results.py
```

| Experiment | Folder | Evidence |
|---|---|---|
| Objective-aware placement and live remaining-work gate | [objective-aware-2026-10-04](objective-aware-2026-10-04/) | New Azure real-model runs; objective and automatic-demand matrices kept separate |
| Azure distributed adaptation and baseline matrix | [azure-vm-2026-10-04](azure-vm-2026-10-04/INDEX.md) | 30 distributed + 3 baseline runs, archived pilots, separate analytical replay |
| Endpoint/context, transition gate and queue ablations | [paper-ablations-2026-10-04](paper-ablations-2026-10-04/INDEX.md) | Decision/model sweeps, synthetic queue measurements, instrumentation calibration |
| Whole-model replicas versus pipeline routing | [product-direction-2026-10-04](product-direction-2026-10-04/INDEX.md) | Synthetic runtime probe and FIFO follow-up |
| Azure component profiling | [azure-d4-2026-09](azure-d4-2026-09/) | Layer timing, reconstruction and single-device measurements |
| Qwen shard correctness | [qwen3-validation](qwen3-validation/) | In-process, end-to-end and relayout checks |
| Standalone deployment smoke check | [standalone-e2e](standalone-e2e/) | Coordinator, agent and worker logs |
| Kubernetes network and worker-loss experiments | [journal-benchmark-2026-09-13](journal-benchmark-2026-09-13/) | Separate `network/`, `worker-loss/`, `analysis/` and `reports/` folders |
| Partition sensitivity sweeps | [partition-sweeps-2026-09](partition-sweeps-2026-09/) | Separate phase-1 and phase-4 CSVs and findings |
| Codespace thermal experiment | [thermal-2026-09-12](thermal-2026-09-12/report.md) | Historical report |

New objective-aware results use:

```text
objective-aware-2026-10-04/
  raw/objective/     latency versus throughput, stable/network tests
  raw/demand/        fixed throughput versus automatic objectives and live budget
  analysis/         per-run and grouped metrics, paired comparisons, figures
  provenance/       schedules, controller hashes, test logs, source snapshots
  README.md         experiment method, measured findings and limitations
```

[catalog.csv](catalog.csv) lists artifacts and their source paths. Historical
`docs/data` experiments are exposed through relative artifact links so existing
paper/document links keep working. Legacy `bench/results` artifacts are copied
into the corresponding experiment folders. New Azure results are stored here
directly. Regenerate the catalog with `python3 scripts/index-results.py`.

Keep pilots, synthetic measurements, analytical predictions and real-model
measurements distinct. A replay row is not an independent real-model trial.
