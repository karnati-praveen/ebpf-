# Handoff — state, and what to do next

For an agent or person picking this up cold. Read in this order:
`docs/RESEARCH_PLAN.md` (the plan and decision rules),
`docs/NOVELTY_AND_ABLATIONS.md` (what is claimable, the ablation matrix),
`deploy/standalone/README.md` (how to run it), then the findings docs.

Ignore any copy of the plan under `~/.claude/plans/` — it predates corrections.
`docs/RESEARCH_PLAN.md` is authoritative.

Branch: `research/phase0-1-measurement`.

## State

| Phase | State | Evidence |
|---|---|---|
| 0 — measurement correctness | **Done** | `docs/phase0-findings.md` |
| 1 — instrumentation / power check | **Done** | `docs/phase1-findings.md`, `cmd/dpsweep` |
| 2 — standalone runtime (no Kubernetes) | **Done, verified end to end** | `docs/data/standalone-e2e/` |
| 3 — Qwen3 shards + KV cache + recovery | **Done, verified** | `docs/data/qwen3-validation/` |
| 4 — cost model | **Measured and wired in** (endpoint + context terms) | `docs/phase4-*`, `docs/data/azure-d4-2026-09/` |
| 5 — decision gate | **Done**: `none` / `hysteresis` / `gate` / `gate-force` | `internal/partition/decider_test.go` |
| 6 — experiments | **Harness ready**; needs the VMs | `bench/vmrun.py`, `bench/vmanalyze.py` |
| 7 — write-up | Blocked on 6 | — |

Not done and not needed for the VM study: proto field for several workers per
machine (plan 2.4 — one worker per VM suffices), the `keinfer` Go launcher
(replaced by `deploy/standalone/*.sh`).

## What was verified, and how

- **Correctness.** Teacher-forced logits vs single-process HuggingFace for six
  layouts × stateless/cached: max |Δ| 2.2e-5, identical tokens. End to end over
  gRPC in both modes. A 14/14 → 18/10 repartition mid-request in cached mode:
  all 40 tokens identical.
- **Closed loop without Kubernetes.** Discovery through node-agent heartbeats,
  a repartition driven by the measured-speed signal, and healing after a worker
  was killed mid-request with identical output.
- **Fault injection.** Network: +80.1 ms on a persistent connection to the
  worker port only, other ports unaffected. Compute: cgroup cap 0.99 → 0.51 CPU.

## Bugs found and fixed along the way (so they are not reintroduced)

- The node agent never set `worker_addr`, so standalone discovery could not have
  worked on real machines.
- Polling `Worker.Stats` for readiness would have reset the busy window the
  router's utilization figure reads.
- Stateless workers made moving layers free, so the break-even experiment could
  not have been run on the old code at all.
- The router replays the **whole chain** on a relayout; reconstruction cost is
  every layer, not the moved ones (break-even 77.9 s, not 26.4 s, for a 0.7×
  derate at ctx 2048).
- Cloud VMs have no thermal zones, so the controller was blind to compute
  faults there; fixed with measured execution speed (`GPU_MODE=measured`).
- The speed probe re-sent stale fault-time speeds between runs.
- With eBPF off the controller had no network signal, making the H3
  "application-only" arm a blind strawman; fixed with application-level link
  telemetry and explicit source selection.
- The Decider dropped `PipelineMs` when keeping a split; a rebuilt Decider
  silently reset the policy.
- **gRPC reconnect backoff contaminated recovery.** Cached connections to a
  worker that died kept failing fast with the stale "connection refused" for
  ~14 s after it was back (default backoff grows to 120 s), so device-loss
  recovery measured gRPC's backoff schedule. Fixed: `internal/peerconn` (2 s
  max backoff) and WaitForReady on control RPCs; same options in the router.
- **SSH hung on node restore.** The restart loop inherited the caller's output
  pipe, so `ssh vm2 start-worker-node.sh` never returned. Fixed: the loop is
  fully detached and ignores SIGHUP.
- A relayout held the old shard while loading the new one, doubling peak
  memory. Every run now records worker PIDs at start and end; a run where a
  worker died for reasons other than the injected loss is flagged
  `contaminated` and excluded by `vmanalyze.py`.

## Next

1. Create the VMs per `deploy/standalone/README.md` §1 (Accelerated Networking
   OFF; never B-series or Spot).
2. `setup-vm.sh` everywhere; `verify_qwen3.py --relayout` once on a VM.
3. Pilot: a short matrix to fix the SESOI and the H3 threshold. **Freeze both
   before the confirmatory runs**, and do not reuse pilot data.
4. Confirmatory matrix per `docs/NOVELTY_AND_ABLATIONS.md` §3.
5. `bench/vmanalyze.py` for the table and verdicts.

## Rules that must not be relaxed

- Never fabricate or interpolate measurements; record failures.
- Four outcomes: benefit / positive-not-meaningful / harm / inconclusive.
  Overlapping CIs do not falsify; "indistinguishable" is not equivalence.
- No "no prior system does X" without a literature check.
- Recovery = time to sustained successful service, not to pre-fault throughput.
- Rejected moves have no observed outcome without the `gate-force` arm.
- VMs cannot establish thermal or physical-heterogeneity claims.
- `bench/results/` is gitignored; commit curated data under `docs/data/`.
- Keep the Kubernetes path working: it preserves the provenance of old results.
