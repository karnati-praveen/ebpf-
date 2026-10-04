# Azure VM results collected 4 October 2026

All analysis inputs below are saved in this workspace. Source VMs:
`vm2` (`52.231.65.69`, coordinator) and `vm3` (`20.196.205.222`, second
CPU worker). The model is Qwen/Qwen3-0.6B, 28 layers, KV cache enabled.

## Inventory

| Location | Contents |
|---|---|
| `raw/vm/` | 30 completed distributed runs: 24 network/compute runs and 6 loss runs |
| `raw/vm-single/` | 3 completed single-device baselines, each 16/16 requests successful |
| `provenance/vm2/archive/` | Earlier pilot and interrupted-run artifacts, including 6 run metadata files; kept separate |
| `provenance/vm2/` | Launch scripts, benchmark logs, worker/controller/router/agent/memory logs, profile, config |
| `provenance/vm3/` | CPU profiling JSON/logs and worker/agent/memory logs |
| `replay/` | vm3 execution of experimental gate helpers: 71 recorded candidates, 710 model evaluation rows, test log |
| `measured-analysis.txt`, `baseline-analysis.txt` | Existing analyser output for the measured experiments |
| `raw/*/runs_summary.csv` | Per-run measured metrics, ready to load in analysis tools |
| `run-inventory.json` | Request counts and contamination flags for all 33 completed runs |
| `SHA256SUMS` | Local integrity manifest |
| `transfer-validation.json` | Verification against source-VM checksums |

The baseline finished at **4:18:16 PM IST**. Its existing script restarted
vm3's worker afterward. The experimental code was run separately in
`/home/azureuser/keinfer-research-20261004` on vm3 with `GOMAXPROCS=1` and
`nice -n 19`; the live controller and worker binaries were not replaced.

Each completed measured run preserves `meta.json`, `requests.csv`, `series.csv`,
`faults.csv`, and `decisions.json`. Pilots, interrupted runs, measured runs and
analytical replay results must remain separate analysis groups.

## Experimental implementation and evidence

New experimental helpers are in `internal/partition/forecast.go`, with the
replay driver in `cmd/gate-replay/` and preparation/validation scripts in
`bench/prepare_gate_replay.py` and `bench/summarize_gate_replay.py`.
The vm3 log records 26 passing Go tests across the partition and replay packages.
These helpers are **not connected to the live controller**. There are no new
live-inference outcome measurements for these policies.

| Experimental arm | Accepted / 71 recorded candidates |
|---|---:|
| Fixed 30-second horizon, 13% margin | 28 |
| Remaining-work horizon, hypothetical 16 / 64 tokens | 0 / 0 |
| Remaining-work horizon, hypothetical 256 / 1024 tokens | 28 / 28 |
| Empirical probability gate, paired historical cost scenarios | 0 |
| Empirical probability gate including past transition durations | See `replay/summary.csv` |
| Online transition calibration | 19 |
| Oracle knowing the next experimental phase boundary | 51 |
| Oracle integrating future recorded telemetry to run end | 32 |

The remaining-work horizon is `min(30 seconds, remaining_tokens *
current_bottleneck_ms / 1000)`. The token quantities represent service capacity,
not actual extra tokens from a finite request. Actual remaining-token progress
was not recorded, so the 16/64/256/1024 budgets are sensitivity settings. This
is not a measured remaining-work-aware serving controller or makespan optimizer.

Probability uses prior 60-second telemetry, at most one snapshot per five-second
block, a minimum of eight cost blocks, and a 90% acceptance fraction. Blocks
remain correlated, and history can straddle a fault-induced regime change.
The transition-uncertainty variant crosses those blocks with at least three
completed, earlier transition observations from the same scenario; this assumes
independence of cost noise and transition-duration noise. Product scenarios are
not additional independent trials. These empirical probabilities are not
validated confidence levels. Rejecting all candidates is not evidence of benefit.

Calibration pools earlier completed observations by scenario, using a running
mean after three observations. Overlapping request disruptions are grouped by
the single executed voluntary decision inside their request intervals, taking
the maximum disruption and the last request completion. Ambiguous intervals
and recovery decisions are excluded. This attribution is approximate: request
logs do not supply explicit per-transition event identifiers. Of 34 observations,
16 compute observations have mean 5382.4 ms and sample SD 1839.0 ms; 18 network
observations have mean 3947.5 ms and sample SD 598.1 ms. The original profile's
transition forecast at context 128 is 3054.3 ms.

Only calibration observations completed strictly before a candidate are used;
this is checked in `replay/validation.json`. The calibration learns from the
recorded policies' outcomes, not outcomes produced by a deployed new policy.

The oracle arms have privileged future information. The future-trace arm
compares one candidate against staying on the recorded split, prices one
transition, and integrates the bottleneck throughput model. It is not a globally
optimal scheduling oracle or an observed counterfactual. Recorded telemetry is
affected by the original policy. Flow timestamps were not retained, so replay
uses the maximum available kernel SRTT with app fallback; it cannot reconstruct
the controller's exact freshest-flow selection. Candidate point costs use the
original recorded decision values. Loss/recovery runs are preserved but excluded
from voluntary candidate replay.

## Reproduce analysis locally

From the repository root:

```bash
python3 bench/vmanalyze.py docs/data/azure-vm-2026-10-04/raw/vm
python3 bench/vmanalyze.py docs/data/azure-vm-2026-10-04/raw/vm-single
python3 bench/prepare_gate_replay.py docs/data/azure-vm-2026-10-04/raw /tmp/gate-replay-input.json
go test ./internal/partition ./cmd/gate-replay
go run ./cmd/gate-replay -input /tmp/gate-replay-input.json -out /tmp/gate-replay-results.jsonl
python3 bench/summarize_gate_replay.py docs/data/azure-vm-2026-10-04
cd docs/data/azure-vm-2026-10-04
sha256sum -c SHA256SUMS
```

The measured analyser's small-repeat bootstrap classifications are exploratory.
They are not a substitute for more independent trials. In this matrix adaptation
improved compute-fault throughput versus static placement by about 25%; the gate
comparison with hysteresis was inconclusive. Network-fault throughput did not
show a clear adaptation benefit.
