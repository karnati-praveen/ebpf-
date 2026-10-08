# Local real-model baseline results

Completed 16/16 runs; 80 requests; 2 failures. Separate-engine reference mismatches: 0.

Three available compute CPUs, one coordination CPU. FP32 cached Qwen3-0.6B and exact reference outputs; seeded 256-token inputs, 32 output tokens; Q=1/2/4/8; whole-request first-available three replicas; three-thread unsplit; fixed per-Q model-capacity or bottleneck layouts. Component profile measured on the campaign host before runs. Empty model stages do not launch workers, leaving those CPUs unused.

additional processes on one host, not physical heterogeneity or adaptive controller superiority; conditions sharing a fixed layout share one restart. Repetition indices are the analysis blocks; intervals are descriptive and unadjusted.

| Arm | Context | Q | Runs | Median TPS | Failures |
|---|---:|---:|---:|---:|---:|
| bottleneck-3x1t | 256 | 1 | 1 | 3.473 | 0 |
| bottleneck-3x1t | 256 | 2 | 1 | 4.829 | 0 |
| bottleneck-3x1t | 256 | 4 | 1 | 5.584 | 0 |
| bottleneck-3x1t | 256 | 8 | 1 | 5.626 | 0 |
| capacity-3x1t | 256 | 1 | 1 | 3.876 | 0 |
| capacity-3x1t | 256 | 2 | 1 | 5.246 | 0 |
| capacity-3x1t | 256 | 4 | 1 | 5.431 | 0 |
| capacity-3x1t | 256 | 8 | 1 | 5.565 | 0 |
| replicas-3x1t | 256 | 1 | 1 | 3.829 | 0 |
| replicas-3x1t | 256 | 2 | 1 | 5.500 | 0 |
| replicas-3x1t | 256 | 4 | 1 | 5.296 | 1 |
| replicas-3x1t | 256 | 8 | 1 | 6.240 | 1 |
| unsplit-3t | 256 | 1 | 1 | 4.443 | 0 |
| unsplit-3t | 256 | 2 | 1 | 4.349 | 0 |
| unsplit-3t | 256 | 4 | 1 | 4.480 | 0 |
| unsplit-3t | 256 | 8 | 1 | 4.476 | 0 |

capacity-3x1t percentage change against each baseline (paired mean, descriptive 95% interval):

| Baseline | Context | Q | Pairs | Change | Interval |
|---|---:|---:|---:|---:|---|
| bottleneck-3x1t | 256 | 1 | 1 | 11.6% | insufficient repeats |
| replicas-3x1t | 256 | 1 | 1 | 1.2% | insufficient repeats |
| unsplit-3t | 256 | 1 | 1 | -12.8% | insufficient repeats |
| bottleneck-3x1t | 256 | 2 | 1 | 8.6% | insufficient repeats |
| replicas-3x1t | 256 | 2 | 1 | -4.6% | insufficient repeats |
| unsplit-3t | 256 | 2 | 1 | 20.6% | insufficient repeats |
| bottleneck-3x1t | 256 | 4 | 1 | -2.7% | insufficient repeats |
| replicas-3x1t | 256 | 4 | 1 | 2.6% | insufficient repeats |
| unsplit-3t | 256 | 4 | 1 | 21.2% | insufficient repeats |
| bottleneck-3x1t | 256 | 8 | 1 | -1.1% | insufficient repeats |
| replicas-3x1t | 256 | 8 | 1 | -10.8% | insufficient repeats |
| unsplit-3t | 256 | 8 | 1 | 24.3% | insufficient repeats |

`analysis.json` retains queue/compute/residual decomposition and uncertainty. The corrected residual includes serialization, dispatch, transport and measurement overhead; it is not pure network latency. Historical synthetic 99.2% queueing claims are not transferred to these measurements.
