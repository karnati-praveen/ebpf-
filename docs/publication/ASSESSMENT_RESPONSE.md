# Response to the supplied publication assessment

Revision date: 8 October 2026. Review source:
[7 October assessment](ASSESSMENT_2026-10-07.md).
Current authoring source: [IEEE manuscript](ieee-manuscript.md).
Earlier long-form manuscripts and the Elsevier export remain historical sources.

This is an implementation and evidence checklist, not a new literature review
or acceptance estimate. The paper adopts the assessment's empirical-study
framing. Existing runtime work is preserved; no new comparative measurements
were created in this editorial follow-up.

| Assessment concern | Current resolution | Still needed |
|---|---|---|
| Broad novelty and overlapping prior systems | Related work covers EdgeShard, DiSCo, STAR, SpotServe, ServerlessLLM, DynoPipe, FlexPipe and the Intel AI-PC preprint; claims emphasize measurement findings | Check final bibliography and venue fit before submission; no matched prior-system comparison exists |
| Incorrect percentage wording | Paper states 65.4% higher throughput, 39.5% reverse loss and 36.1% completion-time reduction; 76.2% above forecast is distinguished from 43.3% below measurement | Preserve denominators in future summaries |
| Gate advantage unsupported | Abstract, results and conclusion state no demonstrated benefit over hysteresis; whole-run results include drain | Independently repeated, matched-start controller comparison; retain negative outcomes |
| Resource-matched alternatives absent | Four-arm local driver and partial observations retained; abstract and contributions no longer imply a completed replica comparison | Finish repeated unsplit/replica/pipeline comparisons and the optimized-engine baseline with explicit CPU, memory, precision and dispatch accounting |
| Breadth and run-level uncertainty | Methods identify runs as units and the ten-block matrix as a planned, incomplete design | Repeat central policy conditions, vary lengths and Q=4/8, and test genuinely heterogeneous or additional physical workers |
| Q>1 saturation heuristic | Restricted-model capacity bound and three-worker counterexample stated; exact finite-concurrency envelope planner and exhaustive checks exist | Real-runtime validation beyond two physical workers; capacity optimization does not guarantee realized throughput |
| Fluid gate confused with finite completion | Paper distinguishes fluid capacity from finite-cohort makespan and states where the relative margin applies | Measure falling concurrency and continuing admission explicitly |
| Forecast ignores active histories | Optional live-context sum records prompt plus accepted output across active requests | Calibrate elapsed weight-loading, serialization, replay and orchestration on held-out data |
| Transition observations grouped by request | Historical 34 grouped estimates are labeled accordingly; existing transition instrumentation provides migration identities | Validate controller-to-resumption migration records in the remote campaign; do not treat concurrent request stalls as independent migrations |
| Synthetic queue finding overgeneralized | 99.2% is explicitly synthetic loopback evidence; remaining residual includes serialization, dispatch and transport | Real-model measurements over actual transport, plus placement and end-to-end ablations with corrected telemetry |
| Recovery correctness too narrow | 18 real-model/gRPC relayout, loss and restart cases at positions 1/4/12 and Q=1/2 retained; exact final sequences and internal gaps reported | Streaming delivery checks, wider schedules and fault-aware replica/retry comparison; coordinator loss and insufficient surviving memory remain outside scope |
| Demo and artifact claims | Manuscript separates execution evidence from comparative performance and leaves public artifact access pending | Fresh captures, usable artifact, installation/license review and a venue-specific demo submission if selected |
| Submission formatting | Editable IEEEtran source and PDF supplied | Select venue, verify current rules and metadata, and review scientific completeness before submission |

Evidence checkpoints can be inspected without running inference:

- [EPYC 7763 completion status](../../results/publication-2026-10-07/main/completion-status.json): 129/320.
- [EPYC 9V74 completion status](../../results/publication-2026-10-07/main-epyc9v74/completion-status.json): 37/320; do not pool CPU strata.
- [Recovery records](../../results/publication-2026-10-07/recovery/checks.jsonl): 18 position-controlled cases.
- [8 October smoke manifest](../../results/calibrated-controller-2026-10-08/smoke/manifest.json): four baseline arms, one repetition, Q=1, single-host loopback; the directory name does not establish controller evaluation.

The strongest unresolved changes are experiments. Writing corrections, runtime
support and a successful PDF build do not replace them. No venue dates from
the assessment have been revalidated, and no submission has been made.
