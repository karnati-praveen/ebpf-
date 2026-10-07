# Local real-model baseline results

Completed 129/320 runs; 644 requests; 0 failures. Separate-engine reference mismatches: 0.

Each serving arm uses FP32, cached Qwen3-0.6B, fixed greedy prompts and the same HTTP/gRPC runtime. Inference workers are restricted to two CPUs; the one-thread unsplit arm leaves one unused. The pipeline layout is fixed at 18/10. Replicas use whole-request first-available dispatch. Coordination has the same remaining host CPUs in every arm.

These are single-host loopback measurements. They do not measure Azure links, physical heterogeneous devices, an optimized serving engine, or adaptive-controller superiority. Repetition blocks restart workers and randomize arm order. Intervals resample blocks; request counts do not increase the independent sample size.

| Arm | Context | Q | Runs | Median TPS | Failures |
|---|---:|---:|---:|---:|---:|
| pipeline-2x1t | 32 | 1 | 4 | 5.921 | 0 |
| pipeline-2x1t | 32 | 2 | 4 | 7.625 | 0 |
| pipeline-2x1t | 32 | 4 | 4 | 7.723 | 0 |
| pipeline-2x1t | 32 | 8 | 4 | 7.739 | 0 |
| pipeline-2x1t | 128 | 1 | 4 | 4.100 | 0 |
| pipeline-2x1t | 128 | 2 | 4 | 4.984 | 0 |
| pipeline-2x1t | 128 | 4 | 5 | 5.086 | 0 |
| pipeline-2x1t | 128 | 8 | 4 | 5.098 | 0 |
| replicas-2x1t | 32 | 1 | 4 | 5.839 | 0 |
| replicas-2x1t | 32 | 2 | 4 | 7.878 | 0 |
| replicas-2x1t | 32 | 4 | 4 | 7.763 | 0 |
| replicas-2x1t | 32 | 8 | 4 | 7.441 | 0 |
| replicas-2x1t | 128 | 1 | 4 | 4.214 | 0 |
| replicas-2x1t | 128 | 2 | 4 | 5.185 | 0 |
| replicas-2x1t | 128 | 4 | 4 | 5.200 | 0 |
| replicas-2x1t | 128 | 8 | 4 | 4.917 | 0 |
| unsplit-1t | 32 | 1 | 4 | 6.130 | 0 |
| unsplit-1t | 32 | 2 | 4 | 6.235 | 0 |
| unsplit-1t | 32 | 4 | 4 | 6.156 | 0 |
| unsplit-1t | 32 | 8 | 4 | 6.164 | 0 |
| unsplit-1t | 128 | 1 | 4 | 4.191 | 0 |
| unsplit-1t | 128 | 2 | 4 | 4.015 | 0 |
| unsplit-1t | 128 | 4 | 4 | 4.199 | 0 |
| unsplit-1t | 128 | 8 | 4 | 4.198 | 0 |
| unsplit-2t | 32 | 1 | 4 | 4.635 | 0 |
| unsplit-2t | 32 | 2 | 4 | 4.965 | 0 |
| unsplit-2t | 32 | 4 | 4 | 4.820 | 0 |
| unsplit-2t | 32 | 8 | 4 | 4.895 | 0 |
| unsplit-2t | 128 | 1 | 4 | 3.511 | 0 |
| unsplit-2t | 128 | 2 | 4 | 3.596 | 0 |
| unsplit-2t | 128 | 4 | 4 | 3.608 | 0 |
| unsplit-2t | 128 | 8 | 4 | 3.698 | 0 |

pipeline-2x1t percentage change against each baseline (paired mean, descriptive 95% interval):

| Baseline | Context | Q | Pairs | Change | Interval |
|---|---:|---:|---:|---:|---|
| replicas-2x1t | 32 | 1 | 4 | 1.9% | [-3.7, 7.6]% |
| unsplit-2t | 32 | 1 | 4 | 28.0% | [18.8, 38.0]% |
| unsplit-1t | 32 | 1 | 4 | -0.7% | [-6.9, 7.9]% |
| replicas-2x1t | 32 | 2 | 4 | -0.9% | [-5.4, 6.5]% |
| unsplit-2t | 32 | 2 | 4 | 54.4% | [49.0, 60.1]% |
| unsplit-1t | 32 | 2 | 4 | 28.9% | [19.7, 42.5]% |
| replicas-2x1t | 32 | 4 | 4 | 0.3% | [-4.4, 5.1]% |
| unsplit-2t | 32 | 4 | 4 | 63.8% | [53.4, 74.3]% |
| unsplit-1t | 32 | 4 | 4 | 31.7% | [22.8, 46.5]% |
| replicas-2x1t | 32 | 8 | 4 | 5.0% | [-3.3, 14.8]% |
| unsplit-2t | 32 | 8 | 4 | 58.5% | [51.5, 67.4]% |
| unsplit-1t | 32 | 8 | 4 | 28.8% | [19.6, 40.8]% |
| replicas-2x1t | 128 | 1 | 4 | 0.9% | [-4.9, 9.6]% |
| unsplit-2t | 128 | 1 | 4 | 16.9% | [14.1, 19.7]% |
| unsplit-1t | 128 | 1 | 4 | 2.6% | [-5.2, 12.6]% |
| replicas-2x1t | 128 | 2 | 4 | -2.7% | [-7.2, 2.6]% |
| unsplit-2t | 128 | 2 | 4 | 41.8% | [36.9, 48.0]% |
| unsplit-1t | 128 | 2 | 4 | 24.8% | [18.8, 31.3]% |
| replicas-2x1t | 128 | 4 | 4 | -2.6% | [-9.3, 4.3]% |
| unsplit-2t | 128 | 4 | 4 | 38.8% | [31.4, 49.1]% |
| unsplit-1t | 128 | 4 | 4 | 22.3% | [12.5, 34.7]% |
| replicas-2x1t | 128 | 8 | 4 | 2.8% | [-2.2, 7.8]% |
| unsplit-2t | 128 | 8 | 4 | 38.8% | [35.1, 42.5]% |
| unsplit-1t | 128 | 8 | 4 | 22.4% | [15.2, 32.3]% |

`analysis.json` retains queue/compute/residual decomposition and uncertainty. The corrected residual includes serialization, dispatch, transport and measurement overhead; it is not pure network latency. Historical synthetic 99.2% queueing claims are not transferred to these measurements.
