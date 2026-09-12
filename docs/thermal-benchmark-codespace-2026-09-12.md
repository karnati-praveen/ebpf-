# Codespace thermal benchmark — 2026-09-12

## Scope and environment

This report records a small comparison of the simulated thermal scenario in
dynamic and static controller modes. Three repetitions were collected for each
mode. These measurements are descriptive and are not evidence of statistical
significance.

- GitHub Codespace: 2 CPUs, 7.8 GiB RAM, no swap, 32 GB root filesystem
- Cluster: kind, with one control-plane and three worker containers sharing one
  physical host and kernel
- Backend: `sim`
- Thermal input: simulated 92 C GPU-temperature override on worker2
- Load: 3 concurrent request threads, prompt length 16, 8 generated tokens
- Warm-up: 3 successful requests before every measured run
- Phases: 20 seconds clean, 60 seconds fault, 20 seconds recovery
- Dynamic controller: 15% improvement threshold, 30-second cooldown

The results must not be described as real GPU heat or real inter-laptop network
performance. The eBPF programs and their flow/sRTT observations were real host
kernel measurements, but all kind nodes shared the Codespace host.

## Per-run results

`TPS` is mean per-request tokens/second. `Idle` is the mean of the harness's
worst-stage idle fraction samples. Success counts and metrics use requests whose
completion timestamps fell strictly inside each fixed phase window.

| Run | Phase | Success | TPS | TTFT (ms) | Idle | Layer ranges | Recovery |
|---|---|---:|---:|---:|---:|---|---|
| Dynamic 1 | Clean | 18/18 (100%) | 2.696 | 388.5 | 0.036 | 0-4 / 4-8 / 8-12 | — |
| Dynamic 1 | Fault | 48/48 (100%) | 2.139 | 480.2 | 0.087 | 4/4/4 -> 5/2/5 | — |
| Dynamic 1 | Recovery | 15/15 (100%) | 2.181 | 457.8 | 0.023 | 5/2/5 | >20 s |
| Dynamic 2 | Clean | 18/18 (100%) | 2.688 | 389.8 | 0.044 | 4/4/4 | — |
| Dynamic 2 | Fault | 45/45 (100%) | 2.118 | 482.1 | 0.104 | 4/4/4 -> 5/2/5 | — |
| Dynamic 2 | Recovery | 18/18 (100%) | 2.082 | 478.1 | 0.068 | 5/2/5 | >20 s |
| Dynamic 3 | Clean | 18/18 (100%) | 2.689 | 389.1 | 0.049 | 4/4/4 | — |
| Dynamic 3 | Fault | 48/48 (100%) | 2.119 | 481.0 | 0.090 | 4/4/4 -> 5/2/5 | — |
| Dynamic 3 | Recovery | 15/15 (100%) | 2.171 | 457.8 | 0.031 | 5/2/5 | >20 s |
| Static 1 | Clean | 18/18 (100%) | 2.694 | 388.5 | 0.041 | 4/4/4 | — |
| Static 1 | Fault | 27/27 (100%) | 1.270 | 837.8 | 0.628 | 4/4/4 | — |
| Static 1 | Recovery | 6/6 (100%) | 1.108 | 896.6 | 0.645 | 4/4/4 | >20 s |
| Static 2 | Clean | 18/18 (100%) | 2.627 | 399.2 | 0.075 | 4/4/4 | — |
| Static 2 | Fault | 24/24 (100%) | 1.184 | 829.1 | 0.639 | 4/4/4 | — |
| Static 2 | Recovery | 9/9 (100%) | 1.107 | 893.7 | 0.648 | 4/4/4 | >20 s |
| Static 3 | Clean | 18/18 (100%) | 2.684 | 390.4 | 0.050 | 4/4/4 | — |
| Static 3 | Fault | 27/27 (100%) | 1.253 | 836.6 | 0.631 | 4/4/4 | — |
| Static 3 | Recovery | 6/6 (100%) | 1.108 | 896.8 | 0.644 | 4/4/4 | >20 s |

Recovery required both worker2's speed factor to return to 1.0 and the clean
layout to be observed. Neither condition pair was observed before the fixed
20-second recovery window ended, so all recovery times are right-censored at
`>20 s`; no recovery time was extrapolated. Dynamic mode retained its protective
5/2/5 split during the measured recovery windows.

Dynamic fault-to-layout-change times were 6.446, 7.515, and 5.278 seconds.

## Three-run means and measured differences

Percentage changes are `(dynamic - static) / static`. Thus negative TTFT and
idle changes mean that dynamic mode measured lower values.

| Phase | Dynamic TPS | Static TPS | TPS change | Dynamic TTFT | Static TTFT | TTFT change | Dynamic idle | Static idle | Idle change |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Clean | 2.691 | 2.668 | +0.9% | 389.1 ms | 392.7 ms | -0.9% | 0.043 | 0.055 | -22.4% |
| Fault | 2.125 | 1.236 | +72.0% | 481.1 ms | 834.5 ms | -42.3% | 0.094 | 0.632 | -85.2% |
| Recovery window | 2.145 | 1.108 | +93.6% | 464.6 ms | 895.7 ms | -48.1% | 0.041 | 0.646 | -93.7% |

Both modes had 100% request success in every measured phase, a difference of
0 percentage points.

## eBPF and cluster evidence

All three node agents reported:

```text
eBPF tcpmon attached (ports 50051-50052)
```

The agents were not restarted during the six measurements. Controller checks
bracketing the runs contained flow records with nonzero sRTT. The final check
contained two flow records with sRTTs of 0.038 and 0.037 ms. This confirms that
the attachment produced samples; the existence of BTF alone was not treated as
proof.

After the comparison:

- all Kubernetes system and application pods were `1/1 Running`;
- all four kind nodes were `Ready`;
- the controller was restored to dynamic mode (`static: false`);
- controller `last_error` was empty;
- 3.3 GiB RAM and 5.9 GB root-disk space remained available.

## Reproduction commands

```bash
python3 bench/run.py --scenario thermal --mode dynamic --tag thermal_codespace_dynamic_r1
python3 bench/run.py --scenario thermal --mode static  --tag thermal_codespace_static_r1
python3 bench/run.py --scenario thermal --mode dynamic --tag thermal_codespace_dynamic_r2
python3 bench/run.py --scenario thermal --mode static  --tag thermal_codespace_static_r2
python3 bench/run.py --scenario thermal --mode dynamic --tag thermal_codespace_dynamic_r3
python3 bench/run.py --scenario thermal --mode static  --tag thermal_codespace_static_r3

python3 bench/analyze_tagged_thermal.py --prefix thermal_codespace
python3 -c 'from bench.run import set_mode; set_mode("dynamic")'
```

Local raw and derived artifacts are preserved under `bench/results/`:

```text
summary.json
thermal_codespace_comparison.csv
thermal_codespace_comparison.json
thermal_codespace_comparison.png
thermal_codespace_{dynamic,static}_r{1,2,3}_{requests,series,phases}.csv
```

The directory is intentionally ignored by Git. This report records the measured
numbers in version control without changing the repository's policy for bulky
or repeated benchmark outputs.

## Codespace resume fix

`make cluster-up` now detects an IP-based control-plane kubelet API endpoint and
replaces it with the stable endpoint:

```text
https://kubeedgeinfer-control-plane:6443
```

The API server certificate contains `DNS:kubeedgeinfer-control-plane`, and
Docker resolves that name to the container's current address after a normal
Codespace restart. The repair is guarded, preserves the original kubelet config,
and restarts kubelet only when the hostname endpoint is absent.

## Follow-up on separate laptops

Repeat the tagged six-run sequence on distinct physical nodes with a
counterbalanced mode order. Use real NVML or CPU-thermal telemetry and genuine
network links. Extend the recovery observation to at least 60 seconds, collect
more repetitions, and retain per-node resource and environmental measurements
before making statistical or real-hardware claims.
