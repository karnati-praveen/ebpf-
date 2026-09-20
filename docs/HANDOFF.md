# Handoff — state, and what to do next

For an agent or person picking this up cold. Read in this order:
`docs/RESEARCH_PLAN.md` (authoritative plan), then `docs/phase0-findings.md`,
`docs/phase1-findings.md`, `docs/phase4-prelim-findings.md`.

**Note:** a stale copy of the plan exists at `~/.claude/plans/*.md` with
pre-correction content (27 splits, SparKV cited as live prior art, "null H1 is
publishable"). **Ignore it.** `docs/RESEARCH_PLAN.md` is authoritative.

## Where things stand

| Phase | State |
|---|---|
| 0 — measurement correctness | **Done**, committed |
| 1 — instrumentation / power check | **Done**, committed |
| 2 — standalone runtime (no K8s) | **Not started** |
| 3 — Qwen shards + KV cache | **Not started** |
| 4 — cost model | **Preliminary measurements done**, model not yet updated |
| 5 — decision gate | Not started |
| 6 — experiments | Blocked on 2/3; needs ≥2 machines |
| 7 — write-up | Blocked on 6 |

Branch: `research/phase0-1-measurement`, pushed.
`gen/pipelinepb/pipeline_grpc.pb.go` is modified in the working tree — a plugin
downgrade (v1.6.2 → v1.5.1), not ours. `git checkout` it; Phase 2.4 regenerates it.

## Results so far

1. **The 3× fidelity gap was the stage count, not model error.** `fidelity.py`
   compared slowest-stage (throughput) against per-request per-token cost
   (latency). Fixed; `partition.Result` now carries `BottleneckMs` and
   `PipelineMs`. Against the right observable the model is good: median error
   −2.2% to −7.9%.
2. **29 candidate allocations**, not 27 — zero-layer stages are allowed
   (`partition.go:66`).
3. **Endpoint cost (lm_head + final norm) is 33–49% of a 14-layer stage** and the
   DP has no term for it, causing a systematic mis-split worth 10.7–15.0%.
4. **Measured crossover**: repartitioning pays at ctx 128/512/1024 and stops
   paying near 2048, because KV reconstruction grows with context (0.47 s → 6.03 s
   for 14 layers). **This is the headline candidate.**

## Next actions, in priority order

### 1. Fix the cost model (highest value, no hardware, ~half a day)
`internal/partition/partition.go`:
- Add endpoint terms to `Input` (e.g. `EmbedMs`, `HeadMs`) applied to the first
  and last **non-empty** stages in `stageCost`. Default 0 so existing behaviour
  and the brute-force cross-check test are unchanged.
- Make per-layer cost context-dependent rather than a scalar `PerLayerMs`.
- Re-run `go run ./cmd/dpsweep` with measured values; regenerate
  `docs/phase1-dpsweep-*.csv`.
- Add a test pinning the 14/14-vs-17/11 mis-split so it cannot regress.

### 2. Get the two missing measurements (~30 min on the warm VM)
Part B of the last spike was never run. Needed:
- **single-device baseline** — TTFT, ITL, completion latency, aggregate
  tokens/sec, completion rate at concurrency 1/2/4/8. Every distributed policy
  must beat this, and at 0.6B it may well win at concurrency 1.
- **direct KV reconstruction timing** — currently derived from prefill per-layer
  cost, not measured end to end.
- **`lm_head` prefill fix** — confirm whether logits are computed over all
  positions; if so, re-measure prefill with last-position-only.

### 3. Then Phase 2 (standalone runtime)
Full subtask list in `docs/RESEARCH_PLAN.md` §4. The three that bite:
`deploy/manifests/controller.yaml:34` is `args: []` so `--mode=k8s` must land in
the same commit that flips the default; `controller.go:302`/`:311` assume one
global worker port; readiness must be RPC-level, not TCP-accept.

## Rules that must not be relaxed

- **Do not fabricate or interpolate measurements.** If a run fails, record the
  failure.
- **Four outcomes, not three**: benefit / positive-but-below-SESOI / harm /
  inconclusive. Overlapping CIs do not falsify; "indistinguishable" is not
  equivalence.
- **No "no prior system does X"** without a literature check. That rule has
  already caught two errors here.
- Withdrawal (SparKV) invalidates conclusions, **not** prior disclosure. The
  transfer-vs-reconstruct novelty is *unestablished*, not open.
- Recovery = time to **sustained successful service**, not to pre-fault
  throughput — a lost worker may permanently reduce capacity.
- Rejected moves have **no observed counterfactual** without a matched
  forced-move arm. Report them as model predictions.
- VMs **cannot** establish thermal or heterogeneity claims (no thermal zones).
- `bench/results/` is gitignored; committed data lives in `docs/`.
- Keep the Kubernetes path working — it preserves provenance of existing results.
