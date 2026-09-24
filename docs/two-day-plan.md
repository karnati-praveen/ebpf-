# Two-day plan to a submittable paper

Written 2026-09-15. Supersedes the scope in `docs/azure-3vm-runbook.md`
(the runbook's *mechanics* still stand; its *priorities* were set before the
4-CPU journal results were re-read).

## Start here: what the existing results actually say

`docs/journal-benchmark-4cpu-2026-09-13.md` already ran the experiment the
Azure plan was built around — netem x {dynamic, static, profileonly} x 3
reps, plus a dynamic/static failure pair. Three findings, and only one of
them is the one the paper has been assuming.

**1. Dynamic loses on netem.** During the fault phase, dynamic vs. static was
**-1.97%** mean request tokens/s, **+0.19%** TTFT, and **+140.84%** worst-stage
idle. Dynamic vs. profile-only was -1.89% / +0.18% / +141.24%. The controller
correctly observed the real 78.8 ms sRTT rise and repartitioned twice — and
the repartition did not pay. This is a real kernel-injected fault, and the
adaptive system is *worse* than the static baseline on it.

**2. Dynamic wins decisively on node failure.** Static delivered **0/6**
requests during the fault and **0/9** during recovery — zero tokens/s, layout
never restored, right-censored at 60 s. Dynamic delivered **42/42** and
**54/54**, healed 4/4/4 to 6/6 layers, restored the original layout 15.99 s
after the node returned, and recorded 3 replays with correctness preserved by
the generation check.

**3. The 72% number is from the simulated fault.** It comes from the thermal
scenario in `docs/thermal-benchmark-codespace-2026-09-12.md` (fault-phase TPS
2.14 dynamic vs. 1.27 static, ~+68%), where the 92 C reading is a simulated
override on a Codespace container. It is the weakest evidence in the
repository and it is the number the paper currently leads with.

**So: the availability result is the paper. The throughput result is not.**

## The reframe

Stop claiming "eBPF + Kubernetes + partitioning is novel" — the four systems
in the related-work table already cover that ground. Claim what the data
supports:

> Continuous kernel telemetry buys **availability and correctness under node
> loss**, not throughput under network degradation. A statically partitioned
> pipeline goes to zero tokens/s when a node dies and does not come back;
> generation-versioned live reassignment holds 100% success across the same
> fault. Under uniform link degradation, repartitioning does not pay — and we
> explain why.

A systems paper that reports a negative result *with a mechanism* is more
credible than one that reports only wins. Finding 1 is an asset, not a
problem, provided you explain it.

## Why dynamic loses on netem — hypothesis and the cheap test

This is a hypothesis from the existing numbers, not an established cause.
Test it first; it is the highest-value hour in the two days.

`internal/partition/partition.go` already allows a stage to take zero layers
(`stageCost` returns 0, dropping the hop) — so under an 80 ms delay the DP
can bypass the degraded node, and the logs show it did change layout. But the
DP's compute term uses `PerLayerMs`, taken from the CR as a **declared
constant** (`deploy/manifests/pipeline.yaml`: `perLayerMs: 30`), while the
link term is a **measured** sRTT. `bench/fidelity.py` reports measured cost is
consistently **3.03-3.24x** the DP's prediction.

That mismatch is directional. With 12 layers over 3 workers, the model
compares 4x30 + 78 = 198 ms against a 6x30 = 180 ms two-stage split and
chooses to drop the node. At the measured ~3x per-layer cost the true
comparison is roughly 4x90 + 78 = 438 ms against 6x90 = 540 ms — where
dropping the node is the *worse* choice. **A measured link cost weighed
against a declared compute cost systematically biases the DP toward dropping
nodes.**

If that holds, the fix is small and it strengthens the paper's own thesis:
telemetry must calibrate the cost *model*, not merely supply its *inputs*.

**Test (Day 1 AM, on kind, no Azure needed):**
1. Derive `PerLayerMs` online in the controller from measured per-stage
   service time instead of reading the CR constant, keeping the CR value as
   the cold-start seed only.
2. Re-run `netem x {dynamic, static, profileonly}` on kind, 3 reps.
3. If dynamic's fault-phase idle penalty disappears, that is the paper's
   second contribution. If it does not, report finding 1 as a negative result
   with this hypothesis tested and rejected — which is still publishable.

Either outcome is a result. Do not skip the test because you fear the answer.

## Day 1

| Block | Work | Output |
|---|---|---|
| AM (3 h) | Online `PerLayerMs` calibration + kind re-run of netem x 3 modes x 3 reps | Finding 1 explained or confirmed |
| PM (3 h) | Azure 3 VMs per `docs/azure-3vm-runbook.md`; patch `bench/run.py` k3s injection; cluster verified (real inter-VM sRTT, not loopback) | Real testbed live |
| PM (2 h) | **failure x {dynamic, static, profileonly} x 3 reps**, recovery window extended from 60 s to 150 s | The paper's headline result, on real machines |
| Eve (1 h) | Monitoring overhead: identical load with the nodeagent DaemonSet running vs. scaled to zero, 3 reps | Closes critique item 3 |

The extended recovery window matters: static's recovery is currently
right-censored at 60 s, so you cannot say whether it *never* recovers or
merely recovers slowly. At 150 s you can state a number or a proper censoring
bound. Reviewers will ask.

## Day 2

| Block | Work | Output |
|---|---|---|
| AM (2 h) | `WITH_GPT2=1` image; failure x dynamic and netem x dynamic with the real model | Closes critique item 1 |
| AM (1 h) | `bench/analyze_journal.py` over all runs; plots; `bench/fidelity.py` re-run post-calibration | Figures |
| PM (4 h) | Write the paper | Draft |
| Eve (2 h) | Revise, check every number against `bench/results/`, submit | Submission |

## What to cut, and not reopen

- **Thermal on new hardware.** Not reachable in two days (see
  `docs/azure-3vm-runbook.md`). Keep the existing numbers, labeled simulated,
  in a clearly-marked subsection. Do not lead with them.
- **A Llama backend.** `docs/gpu-hardware.md` is right that it would
  strengthen the evaluation and right that it is a new component. Not in two
  days. Name it as future work.
- **Statistical significance.** n=3 supports descriptive reporting with CIs,
  which is what `bench/analyze_journal.py` already produces. Claim
  "descriptive, n=3, not a significance test" explicitly, as the existing
  report already does. Do not let the paper drift into significance language.
- **More fault classes.** Two real ones reported well beats five reported
  thinly.

## Venue reality

Two days, with roughly six hours of actual writing, produces a **workshop or
short paper** (6-8 pages): one real testbed, two fault classes, three modes,
n=3, one negative result explained, one availability result that is strong.
That is a coherent submission.

It does not produce a full systems-conference paper. If the deadline you are
working to is a full conference, the honest options are to submit to a
workshop now and extend, or to take the extra week the full version needs.

## The one-line claim to write the paper around

> Under node loss, a statically partitioned pipeline-parallel LLM deployment
> drops to zero served tokens and does not recover; continuous eBPF-derived
> telemetry with generation-versioned reassignment holds 100% request success
> across the same fault at a measured monitoring cost of X%, while preserving
> token-identical output. Under uniform link degradation, repartitioning does
> not pay, and we show why.

Fill in X from the Day 1 evening overhead runs. Every other number in that
sentence already exists in `bench/results/`.
