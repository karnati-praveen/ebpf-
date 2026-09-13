# Journal benchmark on a 4-CPU Codespace (2026-09-13)

## Scope and prominent limitations

This is a descriptive, small-sample evaluation. **It does not establish
statistical significance.** GPU heat and telemetry are simulated; the kind
nodes share one Azure VM and one Linux kernel; `tc netem` is a real
kernel-injected delay but not a physical network or Wi-Fi link; eBPF sRTT is
real because all three attachment logs and live nonzero flow samples were
observed; the distributed benchmark uses the `sim` backend and is not real
GPT-2 inference; and stopping a kind node container is not a physical-machine
failure. A separate CPU GPT-2 fidelity check is reported below.

## Environment

- Source: `main` at `2bcf829525aeca5751b3ad52e82e705e5cbf016f`
  (`Add thermal benchmark report and resilient demo setup`), confirmed current
  with `git pull --ff-only` on 2026-09-13 UTC.
- Host: GitHub Codespace, AMD EPYC 7763, 4 logical CPUs (2 cores/2 threads),
  15 GiB RAM, no swap, initially 8.4 GiB free of a 32 GiB workspace disk.
- Kernel: `6.8.0-1064-azure #72~22.04.1-Ubuntu`, x86-64.
- Docker 29.7.2-2; kind 0.30.0; Kubernetes/kubectl 1.37.0 client and 1.34.0
  nodes; Go 1.27.0; Python 3.14.2.
- Existing user change preserved: `gen/pipelinepb/pipeline_grpc.pb.go` was
  already modified before this work and is excluded from the benchmark commit.

## Preflight failure, cause, and repair

The first cluster looked superficially healthy at node level but failed strict
preflight: CoreDNS was 0/1, local-path-provisioner crash-looped, the pipeline
was `NoWorkers`, all agents repeatedly logged telemetry deadlines, and
cross-node pod TCP timed out. The host had Docker's current bridge rules in the
nftables backend but also a legacy iptables `FORWARD DROP` chain permitting
only `docker0`. Thus IPv4 traffic on the `kind` bridge was dropped, while IPv6
node traffic worked.

The broken ephemeral cluster was recreated with inter-container communication
explicitly enabled, and this narrowly scoped host rule admitted only traffic
whose input and output were the current kind bridge:

```text
iptables-legacy -I DOCKER-USER 1 -i br-380250c710e1 -o br-380250c710e1 -j ACCEPT
```

After that, direct node, pod, service-IP, and DNS A/AAAA probes succeeded.
The Go gRPC client still exceeded its 900 ms deadline when using the service
hostname (despite direct DNS probes completing in under 1 ms), so the running
node-agent DaemonSet was pointed at the stable controller service IP
`10.96.247.81:50053`. This was a live-cluster workaround, not a committed
manifest change. It eliminated current telemetry failures and produced three
fresh node timestamps below one second. The cluster service IP remained stable
through all controller mode rollouts.

Before measurement, all four nodes and every pod in every namespace were
Ready; controller `last_error` was empty; controller, router, three workers,
and three node agents communicated; every agent logged `eBPF tcpmon attached
(ports 50051-50052)`; inference succeeded; nonzero sRTT flows appeared; and
worker2 reported `qdisc noqueue`. `make cluster-up` also repaired a fresh
IP-based kubelet endpoint to the stable control-plane name and subsequently
resumed without another repair.

## Design and exact execution order

All netem runs used unchanged harness defaults: 3 load threads, prompt length
16, 8 generated tokens, 3 warm-ups, 20 s clean, 60 s fault, 20 s recovery,
80 ms netem delay on worker2 `eth0`, `sim` backend, improvement threshold 0.15,
and 30 s cooldown. The order was:

```text
python3 bench/run.py --scenario netem --mode dynamic     --tag netem_4cpu_20260913_dynamic_r1
python3 bench/run.py --scenario netem --mode static      --tag netem_4cpu_20260913_static_r1
python3 bench/run.py --scenario netem --mode profileonly --tag netem_4cpu_20260913_profileonly_r1
python3 bench/run.py --scenario netem --mode profileonly --tag netem_4cpu_20260913_profileonly_r2
python3 bench/run.py --scenario netem --mode dynamic     --tag netem_4cpu_20260913_dynamic_r2
python3 bench/run.py --scenario netem --mode static      --tag netem_4cpu_20260913_static_r2
python3 bench/run.py --scenario netem --mode static      --tag netem_4cpu_20260913_static_r3
python3 bench/run.py --scenario netem --mode profileonly --tag netem_4cpu_20260913_profileonly_r3
python3 bench/run.py --scenario netem --mode dynamic     --tag netem_4cpu_20260913_dynamic_r3
python3 bench/run.py --scenario failure --mode dynamic --tag failure_4cpu_20260913_dynamic_r1
python3 bench/run.py --scenario failure --mode static  --tag failure_4cpu_20260913_static_r1
MPLCONFIGDIR=/tmp/matplotlib-journal python3 bench/analyze_journal.py
MPLCONFIGDIR=/tmp/matplotlib-fidelity python3 bench/fidelity.py
```

The failure pair used 20 s clean, 60 s stopped, and 60 s recovery. It was not
expanded: the static run did not restore successful service within recovery.

## Netem results

The complete per-run, per-phase values—including layouts, generation changes,
replays, fault-to-layout-change and recovery times—are in
`docs/journal-benchmark-4cpu-2026-09-13.csv`. The versioned JSON contains mean,
sample standard deviation, median, t-based 95% CI for n=3, and all percentage
comparisons. Values below are means across three repetitions.

| Phase | Mode | Success | mean req tok/s | delivered tok/s | mean TTFT ms | p95 TTFT ms | worst idle | target sRTT ms | gen transitions |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| clean | dynamic | 100% | 2.713 | 7.2 | 386.14 | 487.27 | 0.0352 | 3.74 | 2 |
| clean | static | 100% | 2.713 | 7.2 | 386.46 | 489.19 | 0.0312 | 4.44 | 0 |
| clean | profileonly | 100% | 2.710 | 7.2 | 387.99 | 488.05 | 0.0334 | 3.56 | 0 |
| fault | dynamic | 100% | 2.220 | 6.8 | 442.32 | 448.90 | 0.5507 | 78.80 | 2 |
| fault | static | 100% | 2.264 | 6.8 | 441.50 | 448.29 | 0.2287 | 78.75 | 0 |
| fault | profileonly | 100% | 2.262 | 6.8 | 441.53 | 448.10 | 0.2283 | 78.88 | 0 |
| recovery | dynamic | 100% | 2.496 | 7.2 | 410.13 | 447.56 | 0.2468 | 50.25 | 2 |
| recovery | static | 100% | 2.677 | 8.4 | 377.74 | 447.91 | 0.0346 | 55.24 | 0 |
| recovery | profileonly | 100% | 2.678 | 8.4 | 377.22 | 445.78 | 0.0315 | 55.19 | 0 |

Dynamic changed layout after 9.97, 6.69, and 6.72 s, and restored the baseline
layout plus a successful request after 10.77, 6.25, and 6.36 s. Static and
profile-only never changed layout; their first post-removal successes occurred
in about 0.93–1.07 s. The elevated recovery sRTT reflects TCP's smoothed RTT
history; every qdisc snapshot after cleanup was `noqueue`.

During the fault, dynamic versus static was -1.97% for mean request tokens/s,
+0.19% for mean TTFT, and +140.84% for worst-stage idle. Dynamic versus
profile-only was -1.89%, +0.18%, and +141.24%, respectively. These results do
not show a netem performance advantage for dynamic mode under this single-host
sim workload; they do show that the controller observed the real sRTT increase
and repartitioned consistently. The n=3 CIs are wide where run-to-run recovery
timing differs and must not be interpreted as significance tests.

## Failure results

| Phase | Mode | successful/total | mean req tok/s | delivered tok/s | mean TTFT ms | replays | layout result |
|---|---|---:|---:|---:|---:|---:|---|
| clean | dynamic | 18/18 | 2.713 | 7.2 | 387.19 | 0 | 4/4/4 layers |
| fault | dynamic | 42/42 | 1.847 | 5.6 | 536.99 | 0 | healed to 6/6 |
| recovery | dynamic | 54/54 | 2.524 | 7.2 | 403.59 | 3 | restored 4/4/4 |
| clean | static | 18/18 | 2.712 | 7.2 | 386.34 | 0 | 4/4/4 layers |
| fault | static | 0/6 | n/a | 0.0 | n/a | 0 | stale 4/4/4 |
| recovery | static | 0/9 | n/a | 0.0 | n/a | 0 | not restored |

Dynamic's changed layout was already visible 0.05 s after the fault phase
marker (the blocking `docker stop` call means this is a bound, not exact
detection latency) and full restoration took 15.99 s after restart. Static
recovery is right-censored at 60 s. Dynamic recorded three request replays in
recovery. The node itself returned Ready before the next experiment.

## Fidelity, validation, and artifacts

`bench/fidelity.py` found measured request cost to be 3.03–3.08 times the DP's
predicted bottleneck cost across the four dynamic runs. Prediction therefore
tracks the run-level direction closely but omits substantial router, Python,
serialization, and scheduling overhead; it is not an absolute latency model.

Raw local artifacts are under `bench/results/`. Each tag has `_requests.csv`,
`_series.csv`, `_phases.csv`, and `_evidence.json`; evidence includes before
and after controller/pipeline state, host resources and health, qdisc before,
during and after, attachment logs, live flows, assignments, and generations.
Derived local artifacts are `journal_4cpu_per_run.csv`,
`journal_4cpu_summary.json`, `journal_4cpu_idle_timeseries.png`, and
`fidelity.png`. `journal_4cpu_real_ebpf_srtt.png` plots only real kernel/eBPF
measurements. The time-series plot uses a zero-based idle-fraction axis and
dashed phase boundaries. Versioned audit artifacts are the same-date CSV and
JSON in `docs/`; raw data and PNGs remain gitignored.

Python compilation and analysis passed. The first Go test attempts were
environment-blocked by read-only caches and then sandbox DNS. With writable
temporary `GOCACHE`/`GOMODCACHE` and authorized module access, `make test`
passed all packages (the partition tests passed; other packages contain no Go
tests).

For the separately requested real-model check, a temporary CPU-only worker
image was built with `WITH_GPT2=1`, and this command was run:

```text
docker run --rm --shm-size=2g -v /workspaces/ebpf-:/repo -w /repo \
  --entrypoint python3 kubeedgeinfer/worker:gpt2-cpu \
  bench/verify_gpt2.py --tokens 2
```

The single-process Hugging Face GPT-2 reference and three-stage distributed
GPT-2 both generated token IDs `[407, 262]` (` not the`): **MATCH**. The real
CPU distributed check measured 146.77 ms TTFT and 8.562 tokens/s. This is a
correctness/fidelity check with one short request, not part of the replicated
sim benchmark and not a performance distribution.

## Repository changes

- `bench/run.py`: refuses tag overwrite and captures controller, pipeline,
  qdisc, health/resource, logs, freshness, errors, and flow evidence.
- `bench/analyze_journal.py`: produces per-run phase metrics, descriptive
  aggregates/CIs, comparisons, versioned CSV/JSON, and phase-marked plots.
- `bench/fidelity.py`: includes uniquely tagged dynamic runs.
- `JOURNAL_BENCHMARK_STATUS.md`: simple live status requested during execution.
- This report and its CSV/JSON audit tables document the measurements.

## Required physical-machine follow-up

Repeat on at least two separately powered physical laptops with genuine routed
network links, synchronized clocks, real NVML or CPU thermal telemetry, and a
real model backend. Use more repetitions, extend recovery beyond 60 s, record
environmental temperature and power state, and avoid claiming hardware,
Wi-Fi, GPU, or statistical generality from this Codespace experiment.

## Postflight

Dynamic mode was restored. All four nodes and every pod were Ready, controller
`last_error` was empty, all three telemetry ages were below 0.55 s, a final
sim request succeeded with zero replays, nonzero eBPF sRTT flows were present,
worker2 qdisc was `noqueue`, about 10 GiB RAM remained available, and 5.8 GiB
disk was free before deleting the temporary GPT-2 image. The GPT-2 test image
was removed after validation and can be rebuilt from the documented command.
