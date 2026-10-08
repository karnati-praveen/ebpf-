# Local real-model baseline results

Completed 32/32 runs; 160 requests; 0 failures. Separate-engine reference mismatches: 0.

Each serving arm uses FP32, cached Qwen3-0.6B, fixed greedy prompts and the same HTTP/gRPC runtime. Inference workers are restricted to two CPUs; the one-thread unsplit arm leaves one unused. The pipeline layout is fixed at 18/10. Replicas use whole-request first-available dispatch. Coordination has the same remaining host CPUs in every arm.

These are single-host loopback measurements. They do not measure Azure links, physical heterogeneous devices, an optimized serving engine, or adaptive-controller superiority. Repetition blocks restart workers and randomize arm order. Intervals resample blocks; request counts do not increase the independent sample size.

| Arm | Context | Q | Runs | Median TPS | Failures |
|---|---:|---:|---:|---:|---:|
| pipeline-2x1t | 32 | 1 | 1 | 5.966 | 0 |
| pipeline-2x1t | 32 | 2 | 1 | 7.572 | 0 |
| pipeline-2x1t | 32 | 4 | 1 | 7.962 | 0 |
| pipeline-2x1t | 32 | 8 | 1 | 8.019 | 0 |
| pipeline-2x1t | 128 | 1 | 1 | 4.089 | 0 |
| pipeline-2x1t | 128 | 2 | 1 | 4.816 | 0 |
| pipeline-2x1t | 128 | 4 | 1 | 4.904 | 0 |
| pipeline-2x1t | 128 | 8 | 1 | 5.114 | 0 |
| replicas-2x1t | 32 | 1 | 1 | 6.153 | 0 |
| replicas-2x1t | 32 | 2 | 1 | 7.853 | 0 |
| replicas-2x1t | 32 | 4 | 1 | 7.864 | 0 |
| replicas-2x1t | 32 | 8 | 1 | 7.933 | 0 |
| replicas-2x1t | 128 | 1 | 1 | 4.244 | 0 |
| replicas-2x1t | 128 | 2 | 1 | 5.063 | 0 |
| replicas-2x1t | 128 | 4 | 1 | 5.137 | 0 |
| replicas-2x1t | 128 | 8 | 1 | 5.057 | 0 |
| unsplit-1t | 32 | 1 | 1 | 5.884 | 0 |
| unsplit-1t | 32 | 2 | 1 | 5.786 | 0 |
| unsplit-1t | 32 | 4 | 1 | 5.821 | 0 |
| unsplit-1t | 32 | 8 | 1 | 5.897 | 0 |
| unsplit-1t | 128 | 1 | 1 | 3.916 | 0 |
| unsplit-1t | 128 | 2 | 1 | 4.075 | 0 |
| unsplit-1t | 128 | 4 | 1 | 4.227 | 0 |
| unsplit-1t | 128 | 8 | 1 | 3.908 | 0 |
| unsplit-2t | 32 | 1 | 1 | 4.828 | 0 |
| unsplit-2t | 32 | 2 | 1 | 4.844 | 0 |
| unsplit-2t | 32 | 4 | 1 | 4.860 | 0 |
| unsplit-2t | 32 | 8 | 1 | 4.824 | 0 |
| unsplit-2t | 128 | 1 | 1 | 3.514 | 0 |
| unsplit-2t | 128 | 2 | 1 | 3.645 | 0 |
| unsplit-2t | 128 | 4 | 1 | 3.658 | 0 |
| unsplit-2t | 128 | 8 | 1 | 3.632 | 0 |

pipeline-2x1t percentage change against each baseline (paired mean, descriptive 95% interval):

| Baseline | Context | Q | Pairs | Change | Interval |
|---|---:|---:|---:|---:|---|
| replicas-2x1t | 32 | 1 | 1 | -3.0% | insufficient repeats |
| unsplit-2t | 32 | 1 | 1 | 23.6% | insufficient repeats |
| unsplit-1t | 32 | 1 | 1 | 1.4% | insufficient repeats |
| replicas-2x1t | 32 | 2 | 1 | -3.6% | insufficient repeats |
| unsplit-2t | 32 | 2 | 1 | 56.3% | insufficient repeats |
| unsplit-1t | 32 | 2 | 1 | 30.9% | insufficient repeats |
| replicas-2x1t | 32 | 4 | 1 | 1.3% | insufficient repeats |
| unsplit-2t | 32 | 4 | 1 | 63.8% | insufficient repeats |
| unsplit-1t | 32 | 4 | 1 | 36.8% | insufficient repeats |
| replicas-2x1t | 32 | 8 | 1 | 1.1% | insufficient repeats |
| unsplit-2t | 32 | 8 | 1 | 66.2% | insufficient repeats |
| unsplit-1t | 32 | 8 | 1 | 36.0% | insufficient repeats |
| replicas-2x1t | 128 | 1 | 1 | -3.7% | insufficient repeats |
| unsplit-2t | 128 | 1 | 1 | 16.4% | insufficient repeats |
| unsplit-1t | 128 | 1 | 1 | 4.4% | insufficient repeats |
| replicas-2x1t | 128 | 2 | 1 | -4.9% | insufficient repeats |
| unsplit-2t | 128 | 2 | 1 | 32.1% | insufficient repeats |
| unsplit-1t | 128 | 2 | 1 | 18.2% | insufficient repeats |
| replicas-2x1t | 128 | 4 | 1 | -4.5% | insufficient repeats |
| unsplit-2t | 128 | 4 | 1 | 34.1% | insufficient repeats |
| unsplit-1t | 128 | 4 | 1 | 16.0% | insufficient repeats |
| replicas-2x1t | 128 | 8 | 1 | 1.1% | insufficient repeats |
| unsplit-2t | 128 | 8 | 1 | 40.8% | insufficient repeats |
| unsplit-1t | 128 | 8 | 1 | 30.9% | insufficient repeats |

`analysis.json` retains queue/compute/residual decomposition and uncertainty. The corrected residual includes serialization, dispatch, transport and measurement overhead; it is not pure network latency. Historical synthetic 99.2% queueing claims are not transferred to these measurements.
