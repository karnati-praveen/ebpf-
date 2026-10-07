# Results audit and interpretation

This report supersedes the earlier pilot manuscript's statement that distributed
real-model experiments were unavailable. Historical reports retain their original
dates and scope. Current paper evidence is exploratory; do not call it
preregistered or statistically conclusive based on labels in an analysis script.

## Canonical evidence inventory

Aliases and copied folder guides are not additional observations. The registry
at `results/experiments.json` identifies these ten unique evidence collections.

| Collection | Evidence retained | Role in the paper and limitation |
|---|---|---|
| objective-aware, Oct 4 | 20 objective + 12 demand CPU Qwen runs; 240 requests; zero failures; 12 demand correctness checks | Principal objective/finite-work results; two or three repeats, closed-loop load, distinct tested snapshots |
| Azure VM, Oct 4 | 30 distributed + 3 single-device runs; 699 requests; 19 failures; six archived pilot/interrupted metadata files | Principal fault results; pilots excluded; all failures retained in static-loss runs |
| Azure D4, September | Per-layer profiles, reconstruction and single-device CSVs; machine metadata | Historical four-vCPU component evidence; cannot substitute its coefficients for later two-vCPU profile |
| Qwen validation | In-process, gRPC, cached/stateless and relayout logs | Correctness in recorded configurations; exact execution host/date not fully retained |
| Standalone E2E | Config and process/smoke logs | Integration evidence; no independent performance study |
| Paper ablations, Oct 4 | 240 placement rows; 18,000 policy rows; 54 queue + 24 calibration windows; 85,116 synthetic RPCs | Analytical cost sensitivity and synthetic timing diagnostics; independent units are windows, not RPCs |
| Product direction, Oct 4 | Synthetic replica/pipeline/routing windows and request logs | Baseline-design diagnostic; does not prove real-model pipeline superiority |
| Journal benchmark, Sept 13 | kind delay/loss simulation results and report | Historical simulation; shared host/kernel; separate GPT-2 fidelity check is not distributed Qwen evidence |
| Partition sweeps, September | Hypothetical and measured-component DP CSVs | Analytical sensitivity only; inspect context/profile/version rather than pooling |
| Thermal, Sept 12 | Historical simulated-temperature report | No retained standalone raw thermal dataset; no real heat/throttling claim |

The 65 completed real-model runs contain **939 requests and 19 failures**.
The 710 replay rows evaluate **71 recorded candidates**, not 710 inference runs.
Archived interrupted trials are preserved outside the completed-run denominator.
No new live experiment was performed during this paper-preparation audit.

## Independent checks performed

`analyze.py` checks 242 entries in the Azure local manifest, 103 objective and 76
demand source entries, and two tested-source archive hashes. It verifies both
compressed and decoded synthetic request hashes and counts (66,003 and 19,113).
All checks passed. These are integrity checks on retained artifacts; they do not
independently authenticate remote execution or repair missing historical provenance.

Synthetic window request counts, failure counts, and RPC/compute/residual means
are independently recomputed from all raw records for 54 queue and 24 calibration
windows. The 240 cost and 18,000 policy rows are counted separately in
`analysis/ablation-audit.json`; they remain analytical rather than live trials.

The objective and demand schedules, completed event ledgers, and metadata counts
agree at 20 and 12; all ledger return codes are zero. No completed primary run
has the unexpected-worker-restart contamination flag. Independent whole-run
objective summaries match the saved summaries within numerical tolerance; the
fault-phase summaries match the old analyzer when actual event times are used.
Recorded demand correctness checks all report exact matches.

The demand snapshot's partition and workload-controller files match current
source. The objective snapshot's partition file differs; its results belong to
that earlier snapshot. Hashes and comparisons are in `analysis/audit.json`.
The legacy adaptation metadata retains git revision
`24e8e7512891e19d06777d55a0ab69e8b380c4b8`; this alone does not certify that every
remote file was clean at execution. Avoid attributing all 65 runs to one binary.

## Main result interpretation

| Contrast | Descriptive estimate | Interpretation |
|---|---:|---|
| Stable Q=2 throughput vs latency objective, N=32 | 7.303 / 4.046 TPS; **+80.5%**, ratio of run medians | Objective choice matters; n=3 per arm |
| Network Q=1 latency vs throughput, N=32 | 4.001 / 2.419 TPS; **+65.4%**, ratio of medians | Whole-policy contrast includes moves; n=2 per arm |
| Network Q=2 latency vs throughput, N=32 | **−15.4%**, ratio of medians | Throughput objective still better at concurrency two |
| Compute fault hysteresis vs static, N=64 | **+25.0%**, ratio of phase medians; **+25.3%**, mean paired change | Adaptation helps this fault-phase measure; n=3; whole-run gain is only about 6.8% |
| Network fault hysteresis vs static, N=64 | Approximately zero phase contrast | No clear phase benefit; adaptive whole-run throughput is lower |
| Demand Q=2 auto-fixed vs throughput, N=64 | **−24.1%**, ratio of whole-run medians | Startup layout and migration cost penalize automatic mode |
| Demand Q=2 auto-remaining vs auto-fixed | **−3.6%**, ratio of medians | No demonstrated remaining-cap benefit; n=2; initial-state/timing confounding |
| Worker loss | Static: 19 failures and zero fault successes; adaptive: zero failures | Recovery path helps in these traces; recovery bypasses voluntary gate |

At Q=2 automatic policies each execute two moves across two runs; remaining-work
mode records four rejected candidates. These counts establish that the mechanism
ran, not that its rejections improved outcomes. Gate-versus-hysteresis and
forced-gate comparisons do not establish gate superiority. Preserve the negative
results in the abstract and discussion rather than selecting only favorable arms.

## Measurement corrections essential for writing

1. **Compute fault:** `compute:0.5` sets a cgroup quota of 0.5 CPU. It does not
   directly impose a model execution-speed multiplier of 0.5 or a thermal fault.
2. **Whole-run denominator:** use the later of nominal end and final request
   completion. Excluding drain can preferentially hide transition costs.
3. **Phase denominator:** use coordinator event-log on/off timestamps, not
   nominal 40/120/60 boundaries. Injection commands take time.
4. **Phase token attribution:** all request tokens are assigned at completion.
   Without token timestamps this is not directly measured phase token emission.
5. **Success metric:** a phase completion fraction describes requests completing
   in that phase, not the eventual success of requests admitted in that phase.
6. **TTFT/ITL:** router TTFT is internal; response completion is client-visible.
   Request-average ITL is not a token-level p95 distribution.
7. **Recovery:** earliest sustained successful completion is not controller heal
   latency, return to original capacity, or proof of repair when no requests failed.
8. **Replication:** paired repeat labels do not mean paired arrival traces.
   Requests within runs and replay scenario products are dependent.
9. **Gate:** static, hysteresis, gate, and gate-force do not cover the missing
   no-hysteresis arm. All primary live arms use the full cost model and `ebpf+app`;
   omitted-cost and telemetry-source live ablations are missing.
10. **Counterfactuals:** forced-gate runs provide some observed forced policy
    outcomes, but not paired execution of every exact rejected candidate.
    Replay/oracle acceptance counts cannot establish serving performance.

## Ablation findings

Endpoint removal raises a selected example's common-reference bottleneck by
12.0%; freezing context raises it by 8.0%. These are model-regret quantities.
Full-reference zero regret is definitional. The full-chain replay example has
a 77.945-s zero-margin and 190.854-s 13%-margin boundary, with eligibility still
required. Neither is an experimentally observed crossover.

Synthetic worker lock wait explains 99.2% of the 149.984-ms residual at 50-ms
service/Q=4. FIFO admission lowers that residual by shifting waiting into
admission, without improving completion in that example. This motivates queue
instrumentation; it does not quantify Azure queue contamination directly.

Replay's approximate transition grouping yields compute/network means 5382.4
and 3947.5 ms against a 3054.3-ms profile forecast. Strictly earlier completed
observations are used for online calibration. Counts fall from 28 accepted
candidates under the fixed gate to 19 under calibration. Benefit remains unknown.
Oracle arms use privileged information, and probability replay is uncalibrated.

The synthetic routing crossover disappears under an available-replica/FIFO
baseline: 20.247 TPS versus the original pipeline's 19.852. The first cyclic
replica router's 14.989 TPS is unsuitable as the sole baseline for a pipeline claim.

## Decisions for the manuscript

Center the paper on observed objective dependence and adaptation limitations.
Use ablations as mechanism diagnostics, retain failures and unfavorable arms,
and call the dataset exploratory. The present artifact supports a complete
working manuscript. It does not support a journal-ready claim of universal
speedup, optimal finite-work migration, consumer-device validation, or measured
eBPF advantage.
