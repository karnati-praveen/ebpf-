# Azure 3-VM runbook (2-hour session)

Three Azure Ubuntu CPU VMs, one k3s cluster, one Claude Code CLI per VM.
This file is the whole plan; each VM's agent reads only its own section.

## What this run is for

Two of the five gaps in the current evaluation, and only two, are reachable
on CPU VMs in two hours:

- **Real network degradation between real machines.** `tc netem` on an actual
  NIC between separate VMs, measured by eBPF `tp_btf/tcp_probe` sRTT across a
  real Azure VNet — not loopback between kind containers on one kernel.
- **Real node failure.** A k3s agent killed on a third machine, with the
  controller's 3 s heartbeat staleness forcing repartition onto survivors.

Each is run in three modes — `dynamic`, `static`, `profileonly` — which is
exactly the "continuous vs. frozen telemetry" ablation the evaluation needs.

## What this run is NOT for (read before spending time on it)

**Thermal is not reachable on Azure CPU VMs.** Two independent blockers:

1. `POST /gpu/override` returns HTTP 409 unless `GPU_MODE=sim`
   (`cmd/nodeagent/main.go:87`). `scripts/deploy-real-hardware.sh` sets
   `GPU_MODE=cputherm` on GPU-less nodes, so `bench/run.py --scenario thermal`
   fails outright on this cluster.
2. `GPU_MODE=cputherm` reads `/sys/class/thermal`. Azure VMs are guests; the
   hypervisor generally exposes no usable thermal zones, so there is nothing
   real to read even if the override were allowed.

Forcing `GPU_MODE=sim` to make thermal "work" reproduces exactly the simulated
result already in `docs/thermal-benchmark-codespace-2026-09-12.md`, on more
expensive hardware. Do not do it. Thermal stays a labeled simulated result;
this run adds two fault classes that are genuinely real.

## VM sizing

Use **D4s_v5** or **F4s_v2** (4 vCPU, 16 GB), Ubuntu 22.04 or 24.04 LTS.

Do **not** use B-series. Burstable VMs throttle on CPU-credit exhaustion,
which is invisible in the benchmark output and silently corrupts every
latency number under exactly the sustained load these runs generate.

## Roles — why not three symmetric agents

VM2 and VM3 are k3s agents. Their total real work is ~10 minutes of setup
plus responding to fault-injection commands. Three agents editing and pushing
the same branch produces merge conflicts, not parallelism.

| VM | Role | Writes code? | Pushes to git? |
|---|---|---|---|
| VM1 | k3s server, control plane, driver. Patches `bench/run.py`, builds images, runs all benchmarks, commits results. | yes | **yes — only VM1** |
| VM2 | k3s agent, worker, netem fault target | no | never |
| VM3 | k3s agent, worker, node-failure target | no | never |

VM2 and VM3 run shell commands and report output. They do not clone for
editing, do not commit, do not push.

## Azure NSG

Open on the VNet subnet, between the three VMs (private IPs only — do not
expose these to the internet):

| Port | Proto | For |
|---|---|---|
| 6443 | tcp | k3s API |
| 8472 | udp | flannel VXLAN |
| 10250 | tcp | kubelet |
| 5000 | tcp | local image registry |

Use the **private** VNet IPs (`10.x.x.x`) everywhere below, not public IPs.
Flannel VXLAN over public IPs will not work.

## Time budget (2 h wall clock)

| T+ | VM1 | VM2 / VM3 |
|---|---|---|
| 0–10 | install k3s server, print token | install docker, kubectl prereqs |
| 10–20 | patch `bench/run.py` for k3s injection (critical path, pure code) | join cluster as agents |
| 20–35 | build + push images, `deploy-real-hardware.sh` | write `registries.yaml`, restart k3s-agent |
| 35–45 | verify eBPF (BTF, real sRTT samples), verify pipeline ready | set up passwordless ssh from VM1 |
| 45–95 | 6 benchmark runs (netem ×3 modes, failure ×3 modes) | idle / observe |
| 95–110 | collect results, write `docs/azure-3vm-results-*.md` | idle |
| 110–120 | commit + push | — |

If you fall behind at T+60, cut to `netem × {dynamic, profileonly}` and
`failure × {dynamic, static}` — four runs. The `profileonly` comparison is the
one that argues for eBPF; do not cut that one.

GPT-2 (`WITH_GPT2=1`) adds a ~1 GB torch download to the image build. It is
**stretch scope only** — attempt it after the sim-backend runs are recorded
and pushed, never before.

## The two handoffs

The three CLIs cannot talk to each other; you are the message bus. There are
exactly two things to copy between them:

1. **VM1 → VM2, VM3**: the k3s join command (server private IP + node token).
2. **VM1 → VM2, VM3**: the `registries.yaml` line printed by
   `deploy-real-hardware.sh`, plus VM1's ssh public key.

Everything else stays on its own VM.

---

# Prompt for VM1 (control plane / driver)

```
You are on Azure VM1, an Ubuntu CPU VM. It is the k3s SERVER and the only
machine that writes code or pushes git. VM2 and VM3 are separate Azure VMs in
the same VNet running their own agents; I relay messages between you.

Repo: https://github.com/karnati-praveen/ebpf-  branch: claude/azure-ubuntu-vm-testing-ywnb2e
Read docs/azure-3vm-runbook.md first. Budget: 2 hours total. Work in this order
and tell me at each numbered step whether it succeeded, with the evidence.

1. Clone the repo, check out the branch. Install docker, curl, python3, and
   confirm /sys/kernel/btf/vmlinux exists (eBPF CO-RE needs it). Report
   `uname -r` and whether BTF is present.

2. Run `./scripts/join-node.sh server`. Give me the exact
   `./scripts/join-node.sh agent <private-ip> <token>` line it prints. Use the
   10.x.x.x VNet address, not a public IP. Then STOP and wait for me to tell
   you VM2 and VM3 have joined.

3. While waiting, do the critical-path code work: bench/run.py injects faults
   with `docker exec kubeedgeinfer-worker2 tc ...` and `docker stop
   kubeedgeinfer-worker3` (see NODE_MID/NODE_LAST at bench/run.py:36 and the
   netem_start/node_stop helpers). None of that works on a k3s cluster of real
   VMs. Patch it so fault injection is configurable:
     - node names come from env (BENCH_NODE_MID, BENCH_NODE_LAST), defaulting
       to the current kind names so the kind path keeps working
     - a BENCH_INJECT=ssh mode that runs netem via
       `ssh <user>@<host> sudo tc qdisc add dev eth0 root netem delay 80ms`
       and node failure via `ssh <user>@<host> sudo systemctl stop k3s-agent
       && sudo /usr/local/bin/k3s-killall.sh`, recovery via
       `sudo systemctl start k3s-agent`
     - qdisc_snapshot() and node_ip() must work in both modes
   Keep the kind path byte-identical in behaviour. Run `make test` and confirm
   the existing partitioner tests still pass. Do not push yet.

4. Generate an ssh key, give me the public key to hand to VM2 and VM3. Once I
   confirm they installed it, verify `ssh <vm2-private-ip> true` and
   `ssh <vm3-private-ip> true` both succeed with no password prompt.

5. After I confirm both agents joined: label them per the instructions
   join-node.sh printed, confirm `kubectl get nodes` shows 3 Ready nodes, then
   run `./scripts/deploy-real-hardware.sh`. It will pause and print a
   registries.yaml snippet for the other machines — give me that snippet
   verbatim, wait for me to confirm, then continue.

6. Verify the telemetry is REAL before benchmarking, and show me the evidence:
   - eBPF loaded and producing flow samples: nodeagent logs plus
     `curl <nodeagent>:9101/links` on each node showing non-zero sRTT
   - the sRTTs are real inter-VM RTTs, not loopback: compare against
     `ping` between the VMs. If sRTT looks like sub-0.1ms loopback, something
     is wrong — tell me instead of proceeding.
   - `kubectl -n kubeedgeinfer get ipl demo` shows a 3-stage assignment
   Do NOT attempt the thermal scenario; runbook section "What this run is NOT
   for" explains why it cannot work here.

7. Run the benchmarks with the patched harness, tagging every run so nothing
   overwrites: netem × {dynamic, static, profileonly}, then failure ×
   {dynamic, static, profileonly}. Between runs confirm the cluster returned
   to 3 healthy stages. Report tokens/sec, p95 latency, failed+replayed
   requests, worst-stage idle, and time-to-recover for each.

8. Write docs/azure-3vm-results-<date>.md: the hardware (VM size, kernel,
   region), what was real (network, node failure, eBPF sRTT) and what was not
   (thermal — state plainly it was not measured here and why), the per-run
   numbers, and the dynamic-vs-profileonly comparison stated as the
   continuous-telemetry result. Label every simulated number as simulated.
   Commit everything (harness patch, results CSV/JSON, the doc) and push to
   claude/azure-ubuntu-vm-testing-ywnb2e. Do not open a pull request.

9. Only if time remains after step 8 is pushed: rebuild the worker image with
   WITH_GPT2=1, switch the CR to backend: gpt2, and repeat netem × dynamic
   with the real model. Push that as a separate commit.

Rules: report failures with the actual command output, never a summary that
hides an error. If a step fails, tell me what failed and what you need from
VM2/VM3 rather than working around it silently. Do not run destructive Azure
CLI commands. Do not weaken the eBPF or telemetry checks to make a run pass.
```

---

# Prompt for VM2 (worker / netem fault target)

```
You are on Azure VM2, an Ubuntu CPU VM. It is a k3s AGENT joining a cluster
whose server is VM1, another Azure VM in the same VNet. I relay messages
between the two machines.

Your scope is deliberately narrow: prepare this machine, join the cluster,
and run fault-injection commands when asked. You do NOT edit code, do NOT
commit, and do NOT push to git. VM1 owns all of that.

1. Report this machine's private VNet IP (10.x.x.x), hostname, `uname -r`,
   `nproc`, total RAM, and whether /sys/kernel/btf/vmlinux exists. If BTF is
   missing, say so loudly — eBPF network telemetry will be dead on this node
   and the whole experiment is compromised.

2. Also check and report: does /sys/class/thermal contain any usable
   thermal_zone*/temp? Report the actual values. I expect none or garbage on
   an Azure guest; I want the evidence either way, because it is the reason
   we are not running the thermal scenario.

3. Install docker and curl. Do not install k3s yet.

4. Wait for me to give you a `./scripts/join-node.sh agent <ip> <token>`
   command from VM1. To run it you need the repo:
   `git clone https://github.com/karnati-praveen/ebpf-` and check out branch
   claude/azure-ubuntu-vm-testing-ywnb2e — read-only, never push from here.
   Run the join command, then tell me the node name it says it will register
   as and the exact `kubectl label` lines it prints, so I can give them to VM1.

5. When I give you a registries.yaml snippet from VM1, run it exactly as
   given, restart k3s-agent, and confirm the service is active.

6. When I give you an ssh public key from VM1, append it to
   ~/.ssh/authorized_keys and confirm permissions are right (700 on ~/.ssh,
   600 on authorized_keys).

7. Then stand by. VM1 will drive netem fault injection over ssh
   (`tc qdisc add dev eth0 root netem delay 80ms`). Verify now that
   `sudo tc qdisc show dev eth0` works and that the primary interface really
   is eth0 — if it is named something else (ens5, enp0s3), tell me the real
   name immediately, because VM1's harness hardcodes it.
   Confirm your user can run `sudo tc` without a password prompt; if it
   prompts, fix that now (ssh-driven injection cannot answer a prompt).

8. While standing by, watch `kubectl`-free local signals if asked: k3s-agent
   journal, `tc qdisc show`, load. Report anything that looks like this VM
   throttling or running out of memory during VM1's benchmark runs — that
   would invalidate the numbers.

Rules: run only what I give you plus the setup above. Report exact command
output including errors. Never push to git from this machine.
```

---

# Prompt for VM3 (worker / node-failure target)

```
You are on Azure VM3, an Ubuntu CPU VM. It is a k3s AGENT joining a cluster
whose server is VM1, another Azure VM in the same VNet. I relay messages
between the two machines.

Your scope is narrow: prepare this machine, join the cluster, and be the node
that gets killed during the failure/healing experiment. You do NOT edit code,
do NOT commit, and do NOT push to git. VM1 owns all of that.

1. Report this machine's private VNet IP (10.x.x.x), hostname, `uname -r`,
   `nproc`, total RAM, and whether /sys/kernel/btf/vmlinux exists. If BTF is
   missing, say so loudly.

2. Also report whether /sys/class/thermal exposes any real thermal_zone*/temp
   values, with the actual numbers — this is evidence for why the thermal
   scenario is not being run on Azure.

3. Install docker and curl. Do not install k3s yet.

4. Wait for me to give you a `./scripts/join-node.sh agent <ip> <token>`
   command from VM1. Clone https://github.com/karnati-praveen/ebpf- and check
   out branch claude/azure-ubuntu-vm-testing-ywnb2e to get the script —
   read-only, never push from here. Run the join command and report the node
   name plus the exact `kubectl label` lines it prints.

5. When I give you a registries.yaml snippet from VM1, run it exactly as
   given, restart k3s-agent, confirm active.

6. When I give you an ssh public key from VM1, append it to
   ~/.ssh/authorized_keys with correct permissions (700 / 600).

7. You are the failure target. VM1 will kill this node over ssh with
   `sudo systemctl stop k3s-agent && sudo /usr/local/bin/k3s-killall.sh` and
   recover it with `sudo systemctl start k3s-agent`. Verify NOW, before any
   benchmark starts, that:
     - /usr/local/bin/k3s-killall.sh exists
     - your user can run both commands via sudo with NO password prompt
     - stopping and restarting k3s-agent actually returns this node to Ready
   Do that stop/start cycle once as a rehearsal and report how long it took
   for the node to come back Ready. If the rehearsal fails, tell me before
   VM1 wastes a benchmark run on it.

8. During VM1's failure runs, capture `journalctl -u k3s-agent` around the
   kill and recovery windows and report the timestamps — VM1 needs them to
   compute real time-to-recover.

Rules: run only what I give you plus the setup above. Report exact command
output including errors. Never push to git from this machine.
```

---

## Failure modes to expect

| Symptom | Cause | Fix |
|---|---|---|
| Agent cannot reach `<server>:6443` | NSG not open, or public IP used | open 6443/tcp on the subnet, use 10.x addresses |
| Pods stuck `ImagePullBackOff` | registries.yaml not applied on VM2/VM3 | apply the snippet, restart k3s-agent |
| `tc: command not found` | `iproute2` missing | `apt-get install -y iproute2` |
| netem applied but sRTT unchanged | wrong interface name (not eth0) | VM2 reports the real name; patch the harness |
| thermal scenario 409s | `GPU_MODE=cputherm` rejects override | do not run thermal on Azure — see above |
| Latency numbers drift between identical runs | B-series CPU-credit throttling | rebuild on D4s_v5 / F4s_v2 |
| Node stays Ready after `systemctl stop k3s-agent` | containers not killed | also run `k3s-killall.sh` |
