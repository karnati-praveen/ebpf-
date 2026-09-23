# Standalone deployment (no Kubernetes)

The full closed loop — measured telemetry, repartitioning, healing — on plain
Linux machines. Kubernetes only ever did three things here (read config, find
workers, write status); standalone replaces them with a JSON config, node-agent
heartbeats and the controller's `/state` endpoint. Repartitioning itself was
always the controller's own gRPC path and is unchanged.

## Topology

| VM | Runs | Faults injected? |
|---|---|---|
| VM1 (coordinator) | controller, router, worker, node agent | **never** — faults must degrade a stage, not the control path |
| VM2 | worker, node agent | yes |
| VM3 (optional) | worker, node agent | yes |

Two VMs are enough for performance and fault-recovery experiments: Qwen3-0.6B
fits on one VM, so the survivor of a lost node can hold the whole model. A
third adds a 3-stage pipeline and, as a different CPU family, real compute
heterogeneity.

## 1. Create the VMs (Azure)

- **Size:** `Standard_D4s_v5` (4 vCPU, 16 GiB) — the SKU the cost model was
  measured on. For heterogeneity make VM3 a `Standard_D4as_v5` (AMD).
  16 GiB matters: at concurrency 8 a single process reached 6.7 GB.
- **Never B-series** (credit-based CPU throttling looks exactly like the compute
  faults under study) and **never Spot** (eviction destroys counterbalancing).
- **Image:** Ubuntu Server 24.04 LTS, x86_64.
- **Networking:** all VMs in the **same VNet and region**, ideally one proximity
  placement group. **Turn Accelerated Networking OFF**: with it on, traffic can
  take the SR-IOV VF and bypass the qdisc `fault.sh network` installs, so the
  network fault may silently do nothing. `fault.sh status` shows packet counts
  on the fault class — if they stay at 0 while the pipeline runs, the fault is
  not in effect.
- **Inbound:** SSH (22). Everything else is VNet-internal and allowed by
  default: 50051 worker, 50053 controller telemetry.

## 2. Set up every VM

```bash
git clone -b research/phase0-1-measurement https://github.com/karnati-praveen/ebpf-
cd ebpf-
./deploy/standalone/setup-vm.sh
```

Installs Go 1.26.1 and a pinned, isolated Python venv (the exact versions the
Qwen3 backend was verified against), builds the binaries, caches the model and
checks eBPF prerequisites. ~10 minutes, mostly the torch download.

## 3. SSH from VM1 to the workers

The experiment driver injects faults over SSH. On VM1:

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519   # if you have no key
cat ~/.ssh/id_ed25519.pub                           # append to ~/.ssh/authorized_keys on VM2/VM3
cat >> ~/.ssh/config <<'EOF'
Host vm2
  HostName <VM2 private IP>
Host vm3
  HostName <VM3 private IP>
EOF
ssh vm2 true && echo ok
```

## 4. Start

```bash
# on EVERY VM, including VM1 (argument: VM1's PRIVATE IP)
./deploy/standalone/start-worker-node.sh <VM1-private-ip>

# on VM1 only (argument: number of worker VMs, VM1 included)
./deploy/standalone/start-coordinator.sh 2
```

Check:

```bash
curl -s localhost:8081/state | python3 -m json.tool | head -40   # assignments, speeds, flows
curl -s -X POST localhost:8080/generate -d '{"prompt_len":64,"max_new_tokens":16}'
```

The controller assigns every worker within seconds of its node agent reporting.
Expect an uneven split (e.g. 18/10 at ctx 512): the last stage also carries the
LM head, which costs as much as several layers.

Logs: `~/keinfer/logs/{controller,router,worker,nodeagent}.log`.
Stop: `./deploy/standalone/stop.sh`.

## 5. Verify correctness on the VMs (once)

```bash
~/keinfer/venv/bin/python bench/verify_qwen3.py --relayout --tokens 32
```

Must print `RELAYOUT OK`: distributed output identical to single-process
HuggingFace across a repartition in the middle of a request.

## 6. Run experiments (on VM1)

```bash
# dry run: print the counterbalanced schedule and the time estimate
python3 bench/vmrun.py --workers 2 --hosts vm2 --target vm2 \
    --scenarios stable:0,network:120,compute:1.0,loss:0 \
    --policies static,none,hysteresis,gate,gate-force --repeats 3 --dry-run

# run it (drop --dry-run); results land in bench/results/vm/<run>/
python3 bench/vmrun.py ...

# the results table and the pre-registered verdicts
python3 bench/vmanalyze.py bench/results/vm --sesoi 0.10
```

Scenario magnitudes:

| Scenario | Magnitude | What it does |
|---|---|---|
| `compute:<cpus>` | CPU cap, e.g. `1.0` | cgroup v2 `cpu.max` on the worker process |
| `contention:<n>` | CPU hogs, e.g. `2` | `stress-ng` beside the worker (noisy neighbour) |
| `network:<ms>` | delay, e.g. `120` | netem on this worker's replies only |
| `loss:0` | — | stops the worker and node agent; restored afterwards |
| `stable:0` | — | no fault |

Use **120 ms** for the network scenario. With the endpoint-corrected cost model
80 ms clears the 15% improvement threshold by only ~1 point at ctx 2048, inside
the model's own error (docs/phase4-prelim-findings.md).

For H3, run the same matrix with `--link-source ebpf`, `app`, and
`ebpf+app`; for the application-only arm also restart the worker nodes with
`EBPF=off` so the agent's measured overhead is that arm's real overhead.

Single-device baseline: `./deploy/standalone/stop.sh` on VM2/VM3, then
`start-coordinator.sh 1` and
`bench/vmrun.py --workers 1 --scenarios stable:0 --policies static`.

## What VMs can and cannot establish

| Claim | VMs |
|---|---|
| Correctness, recovery, healing | yes |
| Controlled compute degradation (quota, contention) | yes |
| Controlled network degradation | yes |
| Cost-model validation | yes |
| **Thermal throttling** | **no** — Azure VMs expose no thermal zones |
| **Physical device heterogeneity, real WiFi, sleep/wake** | **no** |

Compute faults on VMs are *controlled compute degradation*, not thermal
throttling. Report them as such. Thermal and WiFi claims need physical
laptops; the same scripts run there unchanged.

## Troubleshooting

- **Controller shows no assignments.** `tail ~/keinfer/logs/nodeagent.log` on
  each VM: it logs `worker <addr> ready=true` once the worker serves gRPC. If
  not, the worker is still loading or crashed (`logs/worker.log`).
- **`kv cache protocol error`.** Router and workers disagree on `KV_CACHE`.
  Both default to 1; restart both with the same value.
- **eBPF unavailable.** The agent logs why and continues without kernel
  telemetry. It needs root (the start script uses sudo) and
  `/sys/kernel/btf/vmlinux`.
- **Network fault has no effect.** `fault.sh status` — zero packets on class 1:3
  means Accelerated Networking is bypassing the qdisc.
