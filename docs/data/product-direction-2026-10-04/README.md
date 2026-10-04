# Local runtime evidence for the product-direction research

Date: 4 October 2026. This directory accompanies the
[direction report](../../PRODUCT_DIRECTION_2026-10-04.md).

## Scope

These experiments exercise the repository's existing Python worker and router
with **synthetic sleeping computation over localhost**. They are not real-model
inference, a physical multi-machine benchmark, or evidence of product speedup.
The Go controller, node-agent, transition gate and eBPF are not involved.

The purpose is narrower: check how concurrency and placement mode affect this
runtime, and avoid making “always split the model” a product assumption.

Each run uses 28 simulated layers at 5 milliseconds per layer, hidden dimension
1024, prompt length 16 and 16 generated tokens. Router KV mode is enabled.
Simulator outputs do not demonstrate model quality or real KV memory behavior.
Its sleep cost depends on assigned layer count, not prompt/context length. This
probe cannot predict real prefill latency or long-context decoding behavior.
All simulated workers run on the same four-vCPU host. Sleeping compute does not
represent the resource contention, batching or kernel efficiency of real CPUs
or GPUs, and loopback does not represent a home network.

## Experiment design

- Main matrix: pipeline versus full-model replicas; 1, 2 and 3 workers;
  concurrency 1, 2 and 4; three repeats: 54 admission windows.
- Each client sends another request only after the previous request completes.
  Each window admits requests for 30 seconds, then drains outstanding requests.
- Pipeline placement partitions contiguous layer ranges evenly. Replicas each
  hold all 28 layers. The script assigns placements directly through RPC.
- The primary replica comparator is **per-client cyclic routing**, starting at
  each client's index. This can concentrate requests when worker count and
  client count differ. It is not a least-busy scheduler or strong best-runtime
  baseline.
- A focused follow-up compares a three-worker pipeline and three full-model
  replicas at concurrency 4 using **central admission to an available replica**, with three
  additional repeats per mode. It tests whether the main comparison was being
  driven by the weaker routing policy. It remains a synthetic experiment.
- The focused replica policy permits one whole request per replica and waits
  centrally when all replicas are occupied. The pipeline still admits all four
  clients, permitting stage overlap. Client completion and routing-wait times
  are retained separately; internal router TTFT excludes that central wait.
  This simple admission policy does not claim FIFO fairness or native engine
  batching. It is stronger for this simulator than colliding cyclic requests.
- Mode/resource order is counterbalanced across repeats and concurrency order
  rotated. There are only three repeated windows per condition; use descriptive
  ranges, not a statistical-significance or hardware-performance claim.

There are three isolated worker and three router processes. Unused processes
remain idle for cases using fewer workers. All processes are terminated by the
probe's cleanup block. Model assignments and warm-up calls occur before each
case family. Their times are excluded; these runs do not measure transition cost.

A further three-window replica-only follow-up adds FIFO admission after the
non-FIFO available-replica run exposed a long waiting outlier. This is an
exploratory correction of the benchmark policy, not a preregistered confirmatory
experiment. Both datasets are retained. Pipeline scheduling is unchanged.

## Metrics and their limits

`completed_tokens_per_s_full_observation` counts tokens from successful requests
and divides by time from window start through the final outstanding completion.
`completed_tokens_per_s_admission_window` counts only complete requests that
finish inside the 30-second admission window. The latter has boundary effects;
both are retained rather than selecting the more favorable one.

TTFT is the router's internally measured first generated token time. The HTTP
endpoint returns a complete JSON response after generation; it does not stream
that first token to the client. Consequently these TTFT values are **not
client-visible first streamed token latency**. Completion timing comes from the
router; observation/drain timing comes from the probe client.

The aggregate's “mean window p95” averages the three separately calculated p95
values. It is not the p95 of all pooled requests. Raw per-request data is supplied
so a different descriptive summary can be reproduced. There is no independent
device allocation, semantic model correctness check, memory-capacity test,
network fault, worker failure or replay experiment in this probe.

## Reproduce

Requirements: the repository's generated Python RPC modules and the existing
worker/router requirements (`grpcio`, NumPy and protobuf, with compatible
versions). This simulator path does not require Torch or model weights.
Run from the repository root in an environment permitting local socket binds.
Choose fresh output directories; the script refuses an existing directory.

```sh
python docs/data/product-direction-2026-10-04/runtime_probe.py \
  --out /tmp/kubeedgeinfer-main-probe \
  --window 30 --repeats 3 --replica-policy cyclic

python docs/data/product-direction-2026-10-04/runtime_probe.py \
  --out /tmp/kubeedgeinfer-routing-probe \
  --workers 3 --concurrency 4 --window 30 --repeats 3 \
  --replica-policy available
```

Use the existing project requirements/environment rather than assuming this
research script installs dependencies. `analyze_probe.py` additionally needs
Matplotlib:

```sh
python docs/data/product-direction-2026-10-04/analyze_probe.py /tmp/kubeedgeinfer-main-probe
python docs/data/product-direction-2026-10-04/analyze_probe.py /tmp/kubeedgeinfer-routing-probe
```

The first matrix in this directory was run using an isolated scratch predecessor
of the supplied reproduction script. It uses the same primary case logic. The
reproduction script adds parameters, explicit environment isolation and the
available-replica comparator. See metadata for the original environment and routing
policy rather than assuming the newer script's defaults explain every dataset.

```sh
python docs/data/product-direction-2026-10-04/runtime_probe.py \
  --out /tmp/kubeedgeinfer-fifo-probe --modes replicas \
  --workers 3 --concurrency 4 --window 30 --repeats 3 \
  --replica-policy available-fifo
python docs/data/product-direction-2026-10-04/analyze_probe.py /tmp/kubeedgeinfer-fifo-probe
```

## Files

| File | Contents |
|---|---|
| `runtime-probe-meta.json` | Scope, runtime configuration and environment |
| `source-provenance.json` | During-run Git revision, relevant file hashes and package versions; files were not frozen |
| `runtime-probe-summary.json` / `.csv` | Each admission window and drain metrics |
| `runtime-probe-requests.jsonl` | Successful or failed request observations |
| `aggregate.json` / `.csv` | Descriptive means and ranges by condition |
| `throughput.png` / `.svg` | Plot of means with observed run-range bars |
| `routing-baseline/` | Focused non-FIFO available-replica comparator and corresponding files |
| `fifo-baseline/` | Replica-only FIFO follow-up, with client completion and routing-wait observations |
| `server-*.log`, `router-*.log` | Scratch process logs |
| `gate-margin-prediction.json` | Separate algebraic calculation from committed measured components; not measured in these probes |
| `runtime_probe.py`, `analyze_probe.py` | Reproduction and descriptive analysis |

## Interpretation

The completed results below distinguish throughput from queue fairness and retain
the initially weaker comparator. No result establishes real-model speedup.


The completed main matrix contains 54 windows and 1,146 successful requests;
the available-replica comparison contains six windows and 249 successful
requests; the FIFO comparison contains three windows and 129 successful
requests. Total: **63 windows, 1,524 requests, zero request errors**. This is a
successful simulator run, not a physical-device reliability demonstration.

At concurrency one, one worker averaged 7.07 completed tokens/s and three
pipeline stages averaged 6.94. At concurrency four and three workers:

| Mode / policy | Mean tokens/s over full observation | Observed run range |
|---|---:|---:|
| Pipeline, focused comparison | 19.868 | 19.864–19.870 |
| Replicas, per-client cyclic | 14.989 | 14.967–15.030 |
| Replicas, available without FIFO | 20.247 | 20.241–20.253 |
| Replicas, available with FIFO | 20.247 | 20.243–20.254 |

The maximum observed replica queue wait was 31.727 seconds without FIFO and
2.268 seconds with FIFO. Maximum observed client completion was 33.988 seconds
without FIFO and 4.534 seconds with FIFO. A low internal TTFT hid the non-FIFO
waiting outlier. See raw data for all requests, not only medians or p95 summaries.

These exploratory comparisons corrected a weak baseline and then an unfair
admission rule. They were not preregistered confirmatory experiments. The
three policies are retained rather than replacing the unfavorable datasets.
The product implication is to evaluate admission, fairness and workload mode;
there is no justified claim of distributed real-model acceleration here.

![Comparison of routing policies](routing-comparison.png)
