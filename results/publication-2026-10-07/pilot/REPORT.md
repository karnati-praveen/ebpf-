# Local real-model baseline results

Completed 12/12 runs; 48 requests; 0 failures or token mismatches.

Each serving arm uses FP32, cached Qwen3-0.6B, fixed greedy prompts and the same HTTP/gRPC runtime. Inference workers are restricted to two CPUs; the one-thread unsplit arm leaves one unused. The pipeline layout is fixed at 18/10. Replicas use whole-request first-available dispatch. Coordination has the same remaining host CPUs in every arm.

These are single-host loopback measurements. They do not measure Azure links, physical heterogeneous devices, an optimized serving engine, or adaptive-controller superiority. Repetition blocks restart workers and randomize arm order. Intervals resample blocks; request counts do not increase the independent sample size.

| Arm | Context | Q | Runs | Median TPS | Failures |
|---|---:|---:|---:|---:|---:|
| pipeline-2x1t | 32 | 1 | 1 | 2.645 | 0 |
| pipeline-2x1t | 32 | 2 | 1 | 3.503 | 0 |
| pipeline-2x1t | 32 | 8 | 1 | 3.598 | 0 |
| replicas-2x1t | 32 | 1 | 1 | 2.654 | 0 |
| replicas-2x1t | 32 | 2 | 1 | 3.918 | 0 |
| replicas-2x1t | 32 | 8 | 1 | 3.901 | 0 |
| unsplit-1t | 32 | 1 | 1 | 5.403 | 0 |
| unsplit-1t | 32 | 2 | 1 | 3.306 | 0 |
| unsplit-1t | 32 | 8 | 1 | 3.073 | 0 |
| unsplit-2t | 32 | 1 | 1 | 4.030 | 0 |
| unsplit-2t | 32 | 2 | 1 | 4.082 | 0 |
| unsplit-2t | 32 | 8 | 1 | 4.094 | 0 |

Pipeline percentage change against each baseline (paired mean, descriptive 95% interval):

| Baseline | Context | Q | Pairs | Change | Interval |
|---|---:|---:|---:|---:|---|
| replicas-2x1t | 32 | 1 | 1 | -0.3% | insufficient repeats |
| unsplit-2t | 32 | 1 | 1 | -34.4% | insufficient repeats |
| unsplit-1t | 32 | 1 | 1 | -51.0% | insufficient repeats |
| replicas-2x1t | 32 | 2 | 1 | -10.6% | insufficient repeats |
| unsplit-2t | 32 | 2 | 1 | -14.2% | insufficient repeats |
| unsplit-1t | 32 | 2 | 1 | 6.0% | insufficient repeats |
| replicas-2x1t | 32 | 8 | 1 | -7.8% | insufficient repeats |
| unsplit-2t | 32 | 8 | 1 | -12.1% | insufficient repeats |
| unsplit-1t | 32 | 8 | 1 | 17.1% | insufficient repeats |

`analysis.json` retains queue/compute/residual decomposition and uncertainty. The corrected residual includes serialization, dispatch, transport and measurement overhead; it is not pure network latency. Historical synthetic 99.2% queueing claims are not transferred to these measurements.
