# Journal Benchmark Status

Date: 2026-09-13 UTC

We are testing KubeEdgeInfer in a 4-CPU GitHub Codespace. The Kubernetes
cluster has four kind nodes, but all nodes are Docker containers on the same
Codespace VM and share one Linux kernel.

The first cluster had broken IPv4 communication between Docker containers.
The cause was a stale legacy iptables `FORWARD DROP` policy. A firewall rule
limited to the current kind bridge restored communication. Node-agent DNS
still exceeded its 900 ms telemetry deadline, so this running cluster uses the
controller service IP for telemetry. All three agents now report current data.

Preflight passed: all nodes and pods are Ready, the controller has no current
error, eBPF is attached on every worker node, inference succeeds, real nonzero
sRTT flow samples are visible, and worker2 has no stale netem rule.

The experiment compares dynamic, static, and profile-only controller modes.
Each run uses three load threads, a 20-second clean phase, 60 seconds with a
real kernel `tc netem` 80 ms delay, and a 20-second recovery phase. The backend
is simulated GPT-2 behavior, not real GPT-2 inference.

Completed so far:

- netem dynamic r1: 90/90 successful requests
- netem static r1: 93/93 successful requests
- netem profileonly r1: 93/93 successful requests

Completed: nine counterbalanced netem runs and one dynamic/static kind-node
failure pair. Raw files are preserved under `bench/results/` and are never
intentionally overwritten. A separate real CPU GPT-2 check matched the
single-process reference exactly for two generated tokens. Full results are in
`docs/journal-benchmark-4cpu-2026-09-13.md`.
