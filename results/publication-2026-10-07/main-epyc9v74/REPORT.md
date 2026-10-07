# Local real-model baseline results

Completed 37/320 runs; 188 requests; 0 failures. Separate-engine reference mismatches: 0.

Each serving arm uses FP32, cached Qwen3-0.6B, fixed greedy prompts and the same HTTP/gRPC runtime. Inference workers are restricted to two CPUs; the one-thread unsplit arm leaves one unused. The pipeline layout is fixed at 18/10. Replicas use whole-request first-available dispatch. Coordination has the same remaining host CPUs in every arm.

These are single-host loopback measurements. They do not measure Azure links, physical heterogeneous devices, an optimized serving engine, or adaptive-controller superiority. Repetition blocks restart workers and randomize arm order. Intervals resample blocks; request counts do not increase the independent sample size.

| Arm | Context | Q | Runs | Median TPS | Failures |
|---|---:|---:|---:|---:|---:|
| pipeline-2x1t | 32 | 1 | 1 | 5.255 | 0 |
| pipeline-2x1t | 32 | 2 | 1 | 7.027 | 0 |
| pipeline-2x1t | 32 | 4 | 1 | 7.063 | 0 |
| pipeline-2x1t | 32 | 8 | 1 | 7.146 | 0 |
| pipeline-2x1t | 128 | 1 | 1 | 3.656 | 0 |
| pipeline-2x1t | 128 | 2 | 1 | 4.484 | 0 |
| pipeline-2x1t | 128 | 4 | 1 | 4.695 | 0 |
| pipeline-2x1t | 128 | 8 | 1 | 4.708 | 0 |
| replicas-2x1t | 32 | 1 | 2 | 5.237 | 0 |
| replicas-2x1t | 32 | 2 | 1 | 7.114 | 0 |
| replicas-2x1t | 32 | 4 | 1 | 7.210 | 0 |
| replicas-2x1t | 32 | 8 | 2 | 6.965 | 0 |
| replicas-2x1t | 128 | 1 | 1 | 3.717 | 0 |
| replicas-2x1t | 128 | 2 | 2 | 4.731 | 0 |
| replicas-2x1t | 128 | 4 | 2 | 4.546 | 0 |
| replicas-2x1t | 128 | 8 | 2 | 4.694 | 0 |
| unsplit-1t | 32 | 1 | 1 | 5.431 | 0 |
| unsplit-1t | 32 | 2 | 1 | 5.437 | 0 |
| unsplit-1t | 32 | 4 | 1 | 5.339 | 0 |
| unsplit-1t | 32 | 8 | 1 | 5.357 | 0 |
| unsplit-1t | 128 | 1 | 1 | 3.627 | 0 |
| unsplit-1t | 128 | 2 | 1 | 3.798 | 0 |
| unsplit-1t | 128 | 4 | 1 | 3.735 | 0 |
| unsplit-1t | 128 | 8 | 1 | 3.792 | 0 |
| unsplit-2t | 32 | 1 | 1 | 4.254 | 0 |
| unsplit-2t | 32 | 2 | 1 | 4.339 | 0 |
| unsplit-2t | 32 | 4 | 1 | 4.308 | 0 |
| unsplit-2t | 32 | 8 | 1 | 4.496 | 0 |
| unsplit-2t | 128 | 1 | 1 | 2.967 | 0 |
| unsplit-2t | 128 | 2 | 1 | 3.076 | 0 |
| unsplit-2t | 128 | 4 | 1 | 3.198 | 0 |
| unsplit-2t | 128 | 8 | 1 | 3.438 | 0 |

pipeline-2x1t percentage change against each baseline (paired mean, descriptive 95% interval):

| Baseline | Context | Q | Pairs | Change | Interval |
|---|---:|---:|---:|---:|---|
| replicas-2x1t | 32 | 1 | 1 | 3.3% | insufficient repeats |
| unsplit-2t | 32 | 1 | 1 | 23.5% | insufficient repeats |
| unsplit-1t | 32 | 1 | 1 | -3.2% | insufficient repeats |
| replicas-2x1t | 32 | 2 | 1 | -1.2% | insufficient repeats |
| unsplit-2t | 32 | 2 | 1 | 62.0% | insufficient repeats |
| unsplit-1t | 32 | 2 | 1 | 29.3% | insufficient repeats |
| replicas-2x1t | 32 | 4 | 1 | -2.0% | insufficient repeats |
| unsplit-2t | 32 | 4 | 1 | 64.0% | insufficient repeats |
| unsplit-1t | 32 | 4 | 1 | 32.3% | insufficient repeats |
| replicas-2x1t | 32 | 8 | 1 | 7.7% | insufficient repeats |
| unsplit-2t | 32 | 8 | 1 | 58.9% | insufficient repeats |
| unsplit-1t | 32 | 8 | 1 | 33.4% | insufficient repeats |
| replicas-2x1t | 128 | 1 | 1 | -1.6% | insufficient repeats |
| unsplit-2t | 128 | 1 | 1 | 23.2% | insufficient repeats |
| unsplit-1t | 128 | 1 | 1 | 0.8% | insufficient repeats |
| replicas-2x1t | 128 | 2 | 1 | -4.0% | insufficient repeats |
| unsplit-2t | 128 | 2 | 1 | 45.7% | insufficient repeats |
| unsplit-1t | 128 | 2 | 1 | 18.0% | insufficient repeats |
| replicas-2x1t | 128 | 4 | 1 | 7.8% | insufficient repeats |
| unsplit-2t | 128 | 4 | 1 | 46.8% | insufficient repeats |
| unsplit-1t | 128 | 4 | 1 | 25.7% | insufficient repeats |
| replicas-2x1t | 128 | 8 | 1 | 1.5% | insufficient repeats |
| unsplit-2t | 128 | 8 | 1 | 36.9% | insufficient repeats |
| unsplit-1t | 128 | 8 | 1 | 24.2% | insufficient repeats |

`analysis.json` retains queue/compute/residual decomposition and uncertainty. The corrected residual includes serialization, dispatch, transport and measurement overhead; it is not pure network latency. Historical synthetic 99.2% queueing claims are not transferred to these measurements.
