# Venue fit and experiments needed next

The general Elsevier draft can be developed for either requested journal.
This assessment concerns topic and evidence, not predicted acceptance.

| Journal | Verified scope and inferred fit | Suggested emphasis |
|---|---|---|
| Future Generation Computer Systems | Publisher lists distributed systems, infrastructure monitoring, and dynamic resource management; our runtime fits those topics in principle. | Integrated system, telemetry behavior, transition costs, reproducible deployment; broaden hardware/workload evidence. |
| Journal of Parallel and Distributed Computing | Publisher covers theory, design, evaluation, and use of parallel/distributed systems, including edge/cloud platforms and performance analysis. | Precise objectives and assumptions, algorithm scope, matched ablations, finite-work/pipeline prediction limits. |

Scopes are from the publisher's [FGCS description](https://shop.elsevier.com/journals/future-generation-computer-systems/0167-739X)
and [JPDC description](https://shop.elsevier.com/journals/journal-of-parallel-and-distributed-computing/0743-7315).
The emphasis recommendations are our inference. FGCS is the provisional
system-oriented fit; JPDC becomes stronger with a better finite-work model and
controlled placement evaluation. Both need stronger baseline coverage and
independent replication than the current exploratory study.

ScienceDirect's journal-specific guides returned access errors here. Current
abstract length, highlights requirements, reference style, and supplementary
rules remain **unverified**. Use general `elsarticle` now and check the selected
journal's guide before submission. No claims about fees, impact factors,
decision times, acceptance rates, or special-issue eligibility are made.

## Prioritized experiments

| Priority | Question | Controls and arms | Required outcomes |
|---|---|---|---|
| 1 | Does the remaining-work cap help finite workloads? | Fixed horizon / remaining cap / no voluntary movement; same initial layout, snapshot, trace, costs and replay. Initial latency and initial throughput are separate blocks. | Whole-cohort completion/makespan, successful tokens, failures, client latency and transitions; keep negative results. |
| 2 | Is the transition forecast calibrated? | Context, concurrency, split distance and reload condition varied; independent full-chain replay measurements | Explicit event IDs, bias/error on held-out transitions; count a relayout once rather than once per request. |
| 3 | Do cost terms help in live serving? | Full / no endpoint / frozen context / neither, with same trace/source | Actual throughput/latency, layout choices and prediction error; existing model rows only show sensitivity. |
| 4 | Does telemetry choice help? | App-only / eBPF-only / fallback, with other code fixed and queue instrumentation | Detection, stale samples, cost error, serving outcomes and CPU overhead; no blind-source strawman. |
| 5 | Are broader performance claims warranted? | Optimized single-device runtime, fair available-replica baseline, appropriate reproduced prior system | Same model/precision/hardware/workload; peak memory, finite and steady traffic. |
| 6 | Does the intended everyday-device setting work? | Different consumer devices, actual LAN, memory-stressing model, varied lengths/load | Setup effort, real heterogeneity, peak memory; thermal claims require physical sensors/frequency traces. |

For priority 1, consider output budgets 8/16/32/64/128/256 and Q=1/2 with
64-token prompts. Longer outputs change context and replay costs: freeze the
interpolation/calibration procedure rather than keeping a mismatched constant.
Use finite cohorts without future arrivals and sustained traffic as separate
protocols. Determine repeats from pilot run-level variance and an explicit
meaningful effect. A planning floor of ten independent blocks is a suggestion,
not a completed power calculation or journal requirement.

Counterbalance within blocks. Save seeds, full arrival schedules, source hashes,
model revision, dependencies, configs, PIDs and event times. Keep pilots out of
frozen evaluation; predeclare exclusions and retain partial/failed trials in a
ledger. Analyze independent blocks, report points and appropriate uncertainty,
and account for multiple selected contrasts. Match initial conditions before
attributing differences to the horizon alone.

`objective_matrix.py` hardcodes its original schedules and lengths. The proposed
matched-start finite-cohort design requires harness extensions. `vmrun.py`
exposes lengths, concurrency, source variants, gate parameters and durations,
but remains a timed closed-loop load harness. No new remote commands or live
trials were launched in this paper-preparation session.

## Readiness

Completed: integrity audit, independent summaries, positive/negative contrasts,
separated ablations, bounded related work, general Elsevier source/PDF,
numerical bibliography, ten vector figures, three tables, mathematical proofs and application scenarios, flat archive, build
verification, and focused partition/controller/replay tests.

Before claiming a new optimizer: matched-start finite-work outcomes, calibrated
transitions, wider baseline reproduction and independent evaluation. Before
submitting: human author review; identities/affiliations; real contribution,
funding and conflict declarations; public artifact availability; the selected
journal's current guide; final citation versions; and a title/abstract matching
the final evidence. These are author/research tasks, not permissions required
to prepare the working draft.

The draft records Codex assistance without pretending human review has occurred.
Finalize the disclosure after that review. [Elsevier's policy](https://www.elsevier.com/about/policies-and-standards/generative-ai-policies-for-journals)
requires disclosure of generative-AI manuscript assistance and human responsibility.

Optional draft highlights, subject to the selected journal's rules:

- Objective choice changes performance in small distributed Qwen deployments.
- Short workloads can lose throughput while an automatic policy changes layout.
- Remaining-work gating is exercised live; its advantage remains unestablished.
- Queueing and migration forecasts limit telemetry-based placement decisions.
