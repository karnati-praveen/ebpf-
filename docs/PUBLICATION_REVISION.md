# Shardwise publication revision — stopped checkpoint, 7 October 2026

The user stopped the long-running work. Experiments are incomplete; see
`docs/publication/READINESS.md`. Prepared follow-up scripts are saved for a
future explicitly requested continuation.

The target is a **general IEEE conference writing package**, as requested. The
paper is framed as an empirical study of small-model CPU serving, baseline
choice, reconfiguration accounting and measurement pitfalls. It does not claim
that the payback gate beats hysteresis or that partitioning generally beats
replication. No conference submission or public release is performed.

The editable paper is [ieee-manuscript.md](publication/ieee-manuscript.md). Its
IEEEtran LaTeX, bibliography, PDF and figures are in `docs/publication/`.
`manuscript-before-revision.md` retains the older long form;
`manuscript-revised.md` records the assessment's technical and wording fixes.
These are distinct writing formats, not independent experiments.

## Assessment changes implemented

| Review concern | Change and evidence | Boundary |
|---|---|---|
| Incorrect percentage denominators | Corrected 65.4% higher throughput, 39.5% reverse loss, 36.1% completion reduction; transition forecast 76.2% above forecast / 43.3% below measured | Original observations unchanged |
| Broad novelty claims | Empirical framing; EdgeShard, DiSCo, STAR, SpotServe, ServerlessLLM, DynoPipe, FlexPipe and the Intel AI-PC preprint discussed | No matched prior-system ranking |
| Missing whole-model alternatives | Four-arm FP32 Qwen3 matrix: unsplit one/two threads, first-available whole-model replicas, fixed pipeline | One physical host, loopback, seeded token prompts |
| Too few repetitions | Ten randomized restart blocks per condition, contexts 32/128, Q=1/2/4/8, 16 output tokens; run-level analysis and bootstrap intervals | Not a power calculation, equivalence test or additional-model performance study |
| Optimized engine absent | Separate pinned llama.cpp F32 weights/F32 KV, two compute threads, eight continuous-batching slots | Different kernels and HTTP path; separate timing campaign |
| Q>1 heuristic unjustified | Exact optimizer for max(B,P/Q); three-worker counterexample and 1,000 exhaustive randomized checks | Ideal envelope, not achievable runtime throughput |
| Multiple replay histories | Router reports summed prompt+accepted-token histories; optional `--live-replay-context` forecast | Serial replay-work estimate; elapsed transition calibration still required |
| Synthetic queue result overstated | Worker reports compute-lock queue time; router retains per-stage decode timing and optional queue-corrected residual | Residual is not pure RTT; no demonstrated controller benefit |
| Unclear recovery correctness | Eighteen real-Qwen/gRPC checks across relayout/loss/restart, token positions 1/4/12, Q=1/2; exact outputs and internal token gaps saved | Manual orchestration; no streaming delivery or coordinator-loss claim |
| Weak demo evidence | Source-labeled dashboard, workload/decision/recovery panels, stop/restore controls; actual demo screenshots packaged separately | Demo execution is not comparative efficiency evidence |
| Elsevier-only format | IEEEtran conference source, resolved bibliography and verified PDF build | Final venue page/anonymity rules and author details remain to be selected |

## Runtime usage

Use `-objective=auto -workload-url=http://ROUTER:8080/workload` for the live
finite-concurrency envelope planner. `-live-replay-context` opts into the summed
history forecast and also needs live workload telemetry. Missing or stale
telemetry holds voluntary movement and still allows recovery. Set
`APP_LINK_MODE=queue-corrected` on the router to subtract measured worker queue
wait from the application residual; the default remains `residual`.

The `/generate` reply includes `token_times_ms`, `transitions` and
`decode_rpc_timing`. These timestamps describe internal token acceptance.
The HTTP API returns its final JSON; it does not stream those timestamps as
client token delivery. `/transitions` contains recent completed request recovery
records with generation-linked or request-scoped identities.

## Evidence and reproduction

The campaigns are under `results/publication-2026-10-07/`. Driver completion
status and the generated report establish whether each campaign is complete.
The workspace has restarted on different CPU models. `main/` records EPYC
7763, and `main-epyc9v74/` records EPYC 9V74. Matching campaigns can resume on
matching recorded environments; a different-CPU resume is rejected. Partial
observations, completed campaigns and pilots are preserved separately. Consult
completion status rather than assuming that a folder name means a complete
study. Host identity across restarts is not independently authenticated.

The follow-up matrix in `multistage-epyc7763/` adds three workers, a three-CPU
budget, 256-token inputs and 32-token outputs. Its calibrated fixed capacity
and bottleneck layouts are compared with whole-model three replicas and
three-thread unsplit execution. This adds worker and workload breadth but not
physical heterogeneity. The two-laptop test kit and instructions in
[TWO_LAPTOP_TESTS.md](TWO_LAPTOP_TESTS.md) prepare that separate physical study;
they are not themselves measured laptop evidence.

```bash
# CPU dependencies, Python 3.12 used in the campaign:
python3.12 -m venv .venv
.venv/bin/pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install transformers==4.57.1 grpcio==1.84.0 protobuf==7.36.2 numpy==2.5.3
# Download Qwen/Qwen3-0.6B revision c1899de289a04d12100db370d81485cdf75e47ca.
# Model weights and dependency installations are deliberately outside the ZIP.
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 HF_HUB_OFFLINE=1 .venv/bin/python bench/local_publication.py \
  --out results/reproduction --repetitions 10 --concurrency 1,2,4,8 \
  --contexts 32,128 --tokens 16 --requests 4
.venv/bin/python bench/publication_analyze.py results/reproduction
# Same environment and measured code only: add --resume after interruption.
go test ./...
go test -race ./internal/partition ./internal/controller
.venv/bin/python -m unittest discover -s bench -p 'test_*.py'
.venv/bin/python -m unittest discover -s worker -p 'test_*.py'
python scripts/build-ieee.py
```

For the external engine, clone `https://github.com/ggml-org/llama.cpp`, check out
`005a1e127a84cc75bb66be11b43e4f0773564e53`, then run
`scripts/run-optimized-baseline.py --checkout PATH --source results/reproduction
--out results/reproduction-engine` with the same Python environment. The
script builds only the server, converts F32 weights and records hashes. No
benchmark inference runs concurrently with engine compilation/conversion in
this study. Hardware and package checks prevent incompatible resumes.

`python scripts/finalize-publication-results.py` refuses incomplete campaigns,
checks source provenance, writes the local figures and inserts measured results.
`python scripts/build-ieee.py` builds the IEEE PDF and rejects unresolved
citations, missing glyphs, oversized floats and overfull boxes. The bundle script
adds a manifest for every packaged file and verifies ZIP contents.

## Remaining scientific scope

The new evidence does not resolve natural physical heterogeneity, real WAN
transport, long or naturally varying output budgets,
held-out transition calibration, corrected-telemetry controller outcomes,
matched-start continuing-arrival policy studies, or fault-aware replica
availability. These are explicitly bounded claims and future studies in this
empirical paper. Broader methods or deployment claims would require those
experiments. Formatting and more runs cannot establish algorithmic novelty.

Before a venue submission, the authors must review the manuscript, supply the
required author/affiliation metadata and artifact access, choose the venue,
and check that venue's page and review rules. The general IEEE writing package
is an editable artifact, not a claim of acceptance or an automatically submitted
paper.
