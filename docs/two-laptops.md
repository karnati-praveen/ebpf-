# Running KubeEdgeInfer on two laptops

The exact steps to go from two laptops on the same WiFi to a real cluster
running this project — real network latency between two physical machines and
real CPU thermal throttling, instead of the kind demo's simulated versions.

Call them **A** (becomes the k3s server / control plane) and **B** (joins as
an agent). A ends up running the router, controller, a worker and a node
agent; B runs a worker and a node agent. That gives a **2-stage pipeline**.

## Before you start

- **Both laptops must run Linux.** The node agent loads eBPF programs and runs
  privileged with host networking. macOS/Windows can only run the kind demo,
  inside a Linux VM.
- **Both on the same network**, and B must be able to reach A. Find A's LAN
  address with `ip addr` (a `192.168.x.x` / `10.x.x.x` address — *not*
  `127.0.0.1` and not a `172.17.x.x` docker address).
- **Same CPU architecture** on both (both x86_64, or both arm64). Mixed
  architectures need multi-arch image builds — see `laptops.md` §3.
- **Docker on A** (it builds and serves the images). B needs neither docker
  nor Go — it only pulls images.
- Clone this repo on **both** machines.

## 1. Set up laptop A (server)

```bash
git clone https://github.com/karnati-praveen/ebpf- && cd ebpf-
./scripts/join-node.sh server
```

It installs k3s, opens the firewall ports if `ufw` is active, and prints the
exact command to run on B, including the node token:

```
./scripts/join-node.sh agent 192.168.1.23 K10abc...::server:...
```

If the IP it printed is not the one B can reach, use the right one from
`ip addr` in the next step.

## 2. Join laptop B (agent)

On B, paste the command A printed:

```bash
git clone https://github.com/karnati-praveen/ebpf- && cd ebpf-
./scripts/join-node.sh agent <A-ip> <token>
```

It checks it can actually reach A on port 6443 before installing, and fails
with the firewall commands to run if it can't. When it finishes it prints a
`kubectl label ...` line — **run that on A**, for example:

```bash
# on A
kubectl label node <B-hostname> kubeedgeinfer.io/worker=true
kubectl get nodes        # both should be Ready
```

## 3. Deploy (on A)

```bash
./scripts/deploy-real-hardware.sh
```

This builds the images, serves them from a local registry on A, deploys
everything, sets the pipeline to expect the number of workers you actually
have, and — because neither laptop has an NVIDIA GPU — switches the node
agents to **`GPU_MODE=cputherm`**, which reads `/sys/class/thermal` so the
temperatures driving the control loop are your real CPU package temperatures.

It pauses once to have you run three lines on B so k3s trusts A's registry.

## 4. Watch it (on A)

```bash
kubectl -n kubeedgeinfer port-forward svc/router 18080:8080 &
kubectl -n kubeedgeinfer port-forward svc/controller 18081:8081 &
python3 demo/serve.py     # open http://localhost:8000
```

Same dashboard as the kind demo. The differences on real hardware:

- **eBPF sRTT is genuine WiFi latency** between the two laptops, not
  loopback. Expect a few ms and visible jitter rather than ~0.05 ms.
- **Temperatures are real.** The "Inject heat" button will **not** work — it
  only exists for the simulated backend, and the node agent correctly refuses
  it with `409` on real hardware ("real hardware can't be told what
  temperature to be"). To see throttling you must genuinely heat a laptop:

  ```bash
  # on B, while the dashboard is open
  sudo apt install stress-ng && stress-ng --cpu $(nproc) --timeout 300s
  ```

  Watch B's temperature climb; when it crosses the throttle threshold the
  controller migrates layers off B onto A.

Laptop thermal thresholds vary. Check what yours actually does under load and
tune if the defaults (throttle 85 °C, recover 78 °C) don't match:

```bash
watch -n1 'cat /sys/class/thermal/thermal_zone*/temp'   # millidegrees C
kubectl -n kubeedgeinfer set env ds/keinfer-nodeagent \
  CPU_THROTTLE_C=85 CPU_UNTHROTTLE_C=78
```

## What two laptops can and cannot show

| Scenario | Two laptops? |
|---|---|
| Real network latency / degradation | Yes — genuine WiFi, plus `tc netem` over SSH |
| Real thermal throttling | Yes — real CPU package temperature under load |
| Node failure / healing | **No** — needs 3 workers, so there are survivors to redistribute onto |

For the failure scenario add any third machine (a spare laptop, a desktop, or
even a VM) as another agent.

## Troubleshooting

**B won't join / `kubectl get nodes` shows only A.** Firewall on A. Run there:
`sudo ufw allow 6443/tcp && sudo ufw allow 8472/udp && sudo ufw allow 10250/tcp && sudo ufw allow 5000/tcp`

**Pods stuck `ImagePullBackOff` on B.** B doesn't trust A's registry. Re-run
the three lines `deploy-real-hardware.sh` printed, then
`sudo systemctl restart k3s-agent`.

**Router or controller stuck `Pending`.** Some node must carry
`node-role.kubernetes.io/control-plane`; on k3s the server has it
automatically. Check with
`kubectl get nodes -l node-role.kubernetes.io/control-plane`.

**Temperatures read `-1`.** The node agent found no thermal zone (common in
VMs). Real thermal data needs bare metal.

**Everything Ready but `/generate` returns "no pipeline configured".** Give
the controller ~10 s; it re-pushes the layout on a timer. If it persists,
check `kubectl -n kubeedgeinfer logs deploy/controller`.

**A laptop went to sleep.** k3s recovers, but give it a minute; the node
rejoins and the controller repartitions across whatever is alive.
