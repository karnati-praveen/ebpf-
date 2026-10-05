# Continue Shardwise toward a usable personal AI service

Prepared 4 October 2026 from the [direction research](PRODUCT_DIRECTION_2026-10-04.md).
This is a proposed work sequence, not an implemented product or a commitment to
a delivery date. The user wants a small install without Kubernetes. Their actual
hardware is still needed to select the first supported platform.

## First milestone: a useful service on one computer

Build a demonstrable version that lets the owner start one supported model,
send real text from a familiar client, see streamed output, stop it cleanly,
and understand a failure. It must work without a cluster or privileged kernel
collector. A second computer is an enhancement, not a prerequisite to value.

Use one proven local engine through an adapter. Keep the existing Hugging Face
worker and experiment path available. Do not replace the research engine and
attempt feature parity across every runtime in the same change.

If the user uses Windows or macOS, do not present the existing Linux scripts as
the answer. First prove a whole-model adapter and process lifecycle on that OS.
Linux can be the research testbed while the user's platform is a separate product
target. Kernel telemetry and CUDA support do not automatically port with Go.

### The first-run experience to prototype

1. Open the installer and see the detected device and supported engine. Reuse a
   compatible installed engine where possible.
2. Choose one supported model from a small list. Show download size, estimated
   fit and context limit before starting; do not hide the model download behind
   a tiny management-binary claim.
3. Start a service and obtain a stable local endpoint. Open a familiar client
   and complete a chat without placement settings.
4. See a plain status: downloading, loading, ready, paused or unable to serve,
   with a concrete cause and action.
5. Optionally pair another computer through explicit owner approval. Show what
   that computer can contribute and whether using it helps this workload.
6. Stop or pause sharing without losing the service configuration.

This is a proposed flow, not a shipped installer. The first demonstration should
prove steps 1–4 and 6 before promising that another device is required.

## Work sequence and acceptance checks

### 0. Establish the user's real baseline

**Deliverables:** device inventory; one chosen daily task and client; current
single-device engine/model configuration; a reproducible baseline run.

Record OS/architecture, RAM, GPU/VRAM or unified memory, free disk, driver/runtime,
and whether a second separately powered device is available. Record model digest,
quantization, template/tokenizer, context and output length. Test the same task
with the best practical existing single-device setup.

**Acceptance:** we can state the concrete problem without mentioning scheduling
technology, and reproduce it. Examples: a coding helper becomes too slow during
a build; several requests queue on a shared machine; a desired model cannot fit.
If there is no recurring problem, prefer a research/controller project over a
new consumer platform.

### 1. Define a small product intent and runtime contract

**Likely touch points:** `internal/controller/source.go`, a new product-facing
configuration type, and an engine adapter interface. Avoid forcing every
external engine through the existing whole-layer worker protocol.

Proposed intent fields:

| Field | Meaning |
|---|---|
| Model identity | Exact weights/quantization and compatible template/tokenizer |
| Engine | Supported runtime, version and device capability |
| Objective | Interactive latency or concurrent throughput |
| Context/concurrency limits | Admission bounds and memory planning inputs |
| Approved devices | Owner-authorized execution targets |
| Desktop reserve | Capacity retained for the owner, with enforcement mechanism stated |
| Sharing state | Paused, local-only, or allowed on approved peers |

Adapter operations should cover availability, model inventory, load/unload,
generation/streaming, cancellation, measured timings, and capability reporting.
Sharding, live relayout, cache export/import, and replay must be separate optional
capabilities. “Unsupported” is a valid result, not permission to emulate a cheap
operation by an expensive unnoticed restart.

**Acceptance:** one adapter can serve one pinned model; bad model/engine/version
combinations give an actionable error; research profiles are never reused across
incompatible runtime/precision/hardware configurations.

### 2. Add a real text front door

**Likely touch points:** `worker/router.py` or a separate Go/API adapter. Preserve
the research `/generate` endpoint for reproducibility.

Offer a deliberately documented subset of `/v1/models` and
`/v1/chat/completions`, including streaming, bounded input/output, cancellation,
and clear errors. Use the selected model's real chat template and tokenizer.
An existing chat/coding client provides a quick usability test. Broad protocol
compatibility can follow after this subset works.

**Acceptance:** the client completes a real chat, streamed fragments assemble
correctly, disconnecting the client stops unnecessary work, and an unavailable
model or exceeded memory/context limit does not become a generic server error.
Do not claim tool-calling support from protocol shape alone; test the chosen
model/runtime before enabling it.

### 3. Package a rootless default path

**Likely touch points:** a new local launcher/management command; product install
scripts or release artifacts. Keep `deploy/standalone/` as the current research
runbook rather than rewriting its assumptions invisibly.

The package should supply the management binary and select/download one runtime
when needed. Prefer using an existing compatible engine installation. No user
Go build, virtualenv management, Kubernetes, kind or Docker should be needed for
the basic path. Optional engines and model weights have their own download sizes.

Provide commands or UI actions to start, inspect, diagnose, pause and stop. Show
download progress, required disk space, model load progress and memory failure.
Make interrupted downloads recoverable. Clearly separate model assets from
management overhead when reporting install footprint.

**Acceptance:** a clean supported machine reaches a first response using the
documented path; no elevated permission is required for basic single-device
serving; stopping leaves no unwanted processes; the package can be uninstalled
while retaining or deliberately removing model assets. Measure install time,
download size, idle management RSS and background CPU. Set footprint targets
after the first baseline rather than inventing a universal “lightweight” number.

### 4. Make capacity a hard constraint

**Likely touch points:** `internal/partition/partition.go`, model metadata,
`proto/pipeline.proto`, telemetry and runtime inspection.

Represent weights, KV cache, activation/runtime overhead, device-specific
endpoints, and transition peak memory. Reserve headroom; handle shared RAM/VRAM
without double counting. The proposed memory model must be validated against the
chosen runtime's allocated and peak memory.

For the existing research engine, either load only assigned tensors or clearly
reject “larger than any worker” placement. Whole-model transient loading is
incompatible with that capacity promise. A selective loader must handle tied
weights, final norm/head, precision, model metadata and changed boundaries.

[Accelerate's empty initialization](https://huggingface.co/docs/accelerate/usage_guides/big_modeling)
and [Safetensors partial reads](https://huggingface.co/docs/safetensors/main/en/index)
are useful primitives for a selective-loader spike. Neither turns local device
dispatch into a networked inference engine. First validate one model's tensor
selection, tied weights and boundary changes under a constrained memory budget.

**Acceptance:** an infeasible plan is rejected before loading; survivor capacity
is checked after loss; a deliberately constrained worker can load an assigned
shard without holding the whole model if that feature is claimed; peak memory
and output correctness are measured. OOM should produce a retained diagnostic,
not repeated opaque relayout attempts.

### 5. Pair a second device safely

**Likely touch points:** enrollment/state persistence, `internal/peerconn`, Python
server transports, telemetry identity and process management.

Use expiring single-use enrollment material followed by durable peer identity,
protected channels, and revocation. Discovery finds possible peers; it does not
authorize them. Provide manual address entry when discovery fails. Start on a
trusted LAN; do not build public swarms or internet NAT traversal in this milestone.

Persist controller intent and an epoch/fencing rule. Distinguish device transport
health from a model instance that has finished loading and can serve. Prefer one
explicit coordinator before considering automatic leader election.

**Acceptance:** an unpaired node cannot advertise itself into serving membership
or change a layout; a revoked node cannot resume control; restarts recover known
intent; a second controller is rejected/fenced; sleep/wake or disconnect produces
visible states and a documented recovery outcome. The application may continue
with reduced capacity if feasible; it may correctly become unavailable otherwise.

### 6. Compare whole-model routing, replicas and splitting

**Likely touch points:** a planner above the existing layer DP; per-request
measurements; model-residency and admission state.

Do not start with an ML scheduler. Compare a small candidate set using measured
costs and confidence bounds: one whole model on an eligible device, a feasible
set of whole-model replicas, and supported split plans. Use latency for one
interactive request and throughput under a stated multi-request workload.
Account for model load, transfer, queueing and cache affinity.

**Acceptance:** on stable hardware the planner can choose one device even when
others are available; it can prefer replicas when they are more useful; it chooses
a split for a valid capacity case; the decision explanation states predicted
versus measured values. A plan marked “split” is only offered for engines that
actually support it.

### 7. Validate adaptive transitions before exposing them by default

**Likely touch points:** gate parameters, persistent events, transition timing,
and `bench/vmrun.py`/`vmanalyze.py` or a separate product experiment harness.

Measure the entire change: waiting/draining, weight load, control RPCs, replay or
state transfer, interrupted requests, recovery and transition back after a fault.
Use the existing matched `gate-force` approach as a paired experimental proxy,
not an exact same-run counterfactual.

Default voluntary changes to request boundaries/drain. Test in-flight replay
only for an engine where the output contract has been established. Keep device
loss separate from voluntary moves: when staying cannot serve, recovery is a
capacity/correctness question, not an ordinary gain threshold.

**Acceptance:** the controller reduces practically meaningful harm or improves
service under predefined changing conditions relative to simple routing/static
placement and hysteresis; stable behavior does not regress beyond predefined
tolerance; uncertainty and inconclusive outcomes are reported. A failed benefit
test keeps the product simple and the controller experimental.

## Real-hardware evaluation matrix

Use the same engine/model/quantization/context for direct comparisons where
possible. Distinguish a controller comparison (same engine) from a product stack
comparison (different optimized engines). Do not attribute an engine/kernel
speedup to the scheduling policy.

| Question | Essential comparison | Required environment |
|---|---|---|
| Does this help a single user? | Best practical single-device setup vs chosen distributed plan, concurrency 1 | Actual target device(s) and real model |
| Does it help concurrent work? | Single-device batching vs full-model replicas vs a feasible pipeline, same concurrency | Distinct devices; concurrency 1/2/4 where memory permits |
| Does splitting buy capacity? | Per-device budget smaller than full model; shard loading succeeds | Peak memory measurement and a real model requiring aggregation |
| Does adaptation repay its cost? | Static/initially optimized, hysteresis, gate and forced-move arms | Fault durations below and above predicted break-even |
| Can a laptop disappear? | Stable vs process failure, device disconnect, sleep/wake | Separately powered physical machines |
| Does kernel telemetry help? | Application-only vs application plus optional kernel input | Matched policy/runtime, overhead and decision outcomes |
| Is it easy enough? | Existing-tool baseline vs our first-run path | A few willing users on supported hardware; explicit consent and observed tasks |

For a paper, retain the predefined statistical rules and pilot/confirmatory split
from `RESEARCH_PLAN.md`. For product discovery, report task completion and pain
descriptively; a few participants do not validate a whole market.

### Small user-discovery study before expanding the product

Recruit a few willing people with the same broad constraints as the owner and
observe their existing workflow before showing the proposed controller. Ask
what task they last attempted, what failed or became slow, how often it happens,
what workaround they used, and whether a second available computer actually
exists. Record their OS and hardware rather than infer it from enthusiasm.

Then compare the existing-tool path with a prototype on the same task: first
response, stop/restart, interpret a load failure, and optionally pair a device.
Observe task completion, assistance needed, understandable errors, and whether
participants return to the service. Separate interest in a concept from a
recurring problem and demonstrated use. Do not ask leading questions such as
whether they want a “smart Kubernetes.”

No participants were recruited or contacted in this research session; this is
a proposed next step. Do not create a pricing or market-size forecast from this
small discovery study.

### Metrics

- Successful/failed/interrupted requests with a failure class.
- TTFT, inter-token latency and completion latency, including tails.
- Tokens completed over the whole observation window, not only an improved
  steady-state interval after excluding transition downtime.
- Additional transition cost, time to sustained successful service, and
  throughput restoration separately.
- Peak host/GPU memory and CPU/GPU utilization with source/availability states.
- Install/download time, idle management overhead, and time to first usable chat.
- Desktop responsiveness during a representative owner's foreground workload.
- Power/energy only when genuinely measured with an appropriate method. No battery
  saving claim from GPU utilization or temperature alone.

Short faults, ordinary stable periods and insufficient-survivor-capacity cases
must remain in the evaluation. They prevent selecting only examples in which
the most complicated policy looks good.

## Explicit product decision gates

Before confirmatory experiments, choose meaningful tolerances from pilot data
and the user's preferences. These are decision categories, not fabricated target
numbers or measured outcomes.

1. **Need:** users encounter a recurring problem that existing local engines,
   clients or PAIR-like routing do not adequately solve in their setup.
2. **Usability:** the chosen platform completes first-run and recovery tasks
   with tolerable help and honest diagnostics.
3. **Feasibility:** capacity/load plans are enforceable; advertised modes work;
   crashes/sleep/wake preserve the documented output contract.
4. **Benefit:** an uncertainty interval for matched outcome differences clears
   the chosen useful-effect threshold where adaptation is meant to help.
5. **Maintenance:** a tested adapter/API remains practical to maintain across
   runtime updates; hardware support is within the project's resources.

If only usability passes, a thin wrapper may be convenient but has weak product
differentiation. If benefit passes but packaging is burdensome, an integration
or research component may be the better continuation. If measurements are
inconclusive, report that and narrow the scope rather than claim “no effect.”
If sufficient survivor memory is unavailable, report reduced/unavailable service
rather than advertise universal self-healing.

## Build-versus-integrate spike

Keep this bounded: inspect one supported extension path in an existing runtime,
prove one controllable engine, and decide from the prototype rather than a
marketing feature list.

| Route | Why investigate | What must be proved |
|---|---|---|
| Independent lightweight controller + one engine | Preserves control ownership and a small coherent product | First-run ease, state persistence, safe process management and a measured advantage |
| Adaptive planner alongside PAIR-like routing | Reuses existing desktop pairing/engine UX | A supported integration boundary, accepted plan/control operations and distinguishable benefit |
| Adaptive placement in LocalAI or another runtime | Reuses catalog, runtime/API support | Backend-level control capability and transition cost without adding unwanted infrastructure |
| Research controller only | Lowest disruption to current work | Complete rigorous hardware experiments and a defensible measured result |

An OpenAI-shaped inference endpoint is an integration point for generating
text; it is not by itself an integration point for placement or live relayout.
No upstream collaboration, message or publication has been initiated.

### Concrete adapter spike: start with documented local APIs

An Ollama adapter can begin with its documented
[`/api/chat`](https://docs.ollama.com/api/chat) stream, response timing fields
from [`/api/generate`](https://docs.ollama.com/api/generate), and
[`/api/ps`](https://docs.ollama.com/api/ps) for resident model identity, context
and reported VRAM allocation. `keep_alive` controls residency. Time the first
received content at the adapter as well: aggregate engine timings are not the
client's TTFT, and reported current allocation is not a future peak-memory proof.

For a direct llama.cpp process, the upstream
[server guide](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
documents streaming APIs, slot state and opt-in metrics including processing
and deferred requests. These are useful application-level inputs for a planner.
Its slot-cache save/restore APIs do not by themselves establish that a cache can
move to a different model, shard layout, build or device configuration.

Bound the spike to one pinned engine version and one model: inventory the model,
serve a streamed chat, measure load and completion, exercise stop/unload, verify
client-disconnect behavior, restart the process, and confirm actionable errors.
Compare the direct engine with the adapter under the same task to measure proxy
overhead. A successful whole-model adapter does not count as a sharding or live
relayout implementation. Use runtime-native batching as a baseline rather than
the research worker's one-compute-lock policy.

## Work to defer

- A general container scheduler, ingress/storage/secrets platform or Kubernetes
  replacement API.
- Supporting every model family, OS, GPU, modality or engine immediately.
- Public volunteer swarms, cloud billing and an automatic device marketplace.
- Custom UI features already supplied by a suitable chat/coding client.
- Automatic paid cloud fallback or silently changing model quality.
- Learned placement policies before a simple measured baseline is evaluated.
- Claims about universal speedup, energy savings, zero downtime or algorithmic
  novelty before the supporting measurements exist.

The existing paper plan defers polished desktop packaging until Phase 6. This
new product plan records the user's requested direction without rewriting past
experiment provenance or implying that Phase 6 has been completed. A one-device
usability spike can inform the next choice while the controlled measurement
work continues on its own terms.
