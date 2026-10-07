# Tests to run on your laptop and your friend's laptop

These are the most useful real-world tests for the Shardwise paper. Start with
the connection check. Keep raw results even when the pipeline loses or a
request fails. The kit measures actual Qwen3 inference; it does not fabricate
network, temperature or speed readings.

**Supported starting setup:** Linux, or Ubuntu under WSL on Windows, on both
laptops. Use the same Python 3.12 environment and packages. The coordinator
scripts require Linux/WSL; native Windows and macOS have not been verified.
Both machines should have at least 8 GB RAM (16 GB preferred), around 5 GB free
disk, and enough available memory for a roughly 2.4 GB FP32 model plus the
runtime. On Windows, check available WSL memory too. Start on the same trusted
Wi-Fi or wired LAN. Record the actual laptop hardware and connection type.

The short test below uses the provided `bench/lan_agent.py` and
`bench/lan_publication.py`. These agents control only their own model processes.
No SSH or administrator access is needed by the scripts. The worker's gRPC
port is unencrypted: keep the kit on your trusted local network.

## 1. Prepare both laptops

Copy the same two-laptop test kit to both laptops and open a terminal in its
folder. Run these commands on **both** laptops:

```bash
python3.12 -m venv .venv
.venv/bin/pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install transformers==4.57.1 grpcio==1.84.0 protobuf==7.36.2 numpy==2.5.3
```

The first benchmark downloads `Qwen/Qwen3-0.6B`, pinned to revision
`c1899de289a04d12100db370d81485cdf75e47ca`, on each laptop. Allow this one-time
download to finish before assessing experiment speed. CPU execution uses FP32
weights and KV caching on both machines.

Write down each laptop's LAN IP. The examples below use **192.168.1.10** for
your laptop and **192.168.1.20** for your friend's. Replace them with your real
addresses. If Windows/WSL cannot accept inbound connections from the other
laptop, resolve WSL networking/firewall reachability first or use native Linux;
an IP shown inside WSL is not automatically reachable from the LAN.

Generate one shared random lab token on your laptop:

```bash
.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(24))'
```

Set that same value in every terminal used below, on both laptops:

```bash
export SHARDWISE_LAB_TOKEN='paste-the-shared-random-value-here'
```

The token is required for control, and is not stored in benchmark results.
Do not include it when sharing results.

On **your laptop**, leave this running:

```bash
.venv/bin/python bench/lan_agent.py --advertise 192.168.1.10
```

On **your friend's laptop**, leave this running:

```bash
.venv/bin/python bench/lan_agent.py --advertise 192.168.1.20
```

The laptops need to reach each other's TCP ports **56080** (lab control),
**56100** (worker), and **56120** (replica HTTP). Guest/campus Wi-Fi may isolate
clients. If connection fails, try a wired LAN or a Wi-Fi network that allows
laptop-to-laptop traffic. Stop with Ctrl+C after testing; the agents clean up
only their own child processes.

## 2. Required first test: connection and exact-output smoke check

Open a **second terminal on your laptop**, set the token as above, then run:

```bash
.venv/bin/python bench/lan_publication.py \
  --local http://192.168.1.10:56080 --peer http://192.168.1.20:56080 \
  --out results/laptop-smoke --repetitions 1 --contexts 32 \
  --concurrency 1,2 --tokens 8
.venv/bin/python bench/publication_analyze.py results/laptop-smoke
```

This is **8 runs**: four serving setups × two concurrency levels. It should
finish with `complete: true` in `completion-status.json`. Inspect `REPORT.md`
and `runs.jsonl`: all requests should match the reference tokens. Keep any
mismatch/error log and resolve it before the longer matrix. This small test
checks connectivity and execution; it is not enough for a publication claim.

## 3. Highest-priority performance test: pipeline versus real baselines

After the smoke check passes, run:

```bash
.venv/bin/python bench/lan_publication.py \
  --local http://192.168.1.10:56080 --peer http://192.168.1.20:56080 \
  --out results/laptop-main --repetitions 10 --contexts 32,128 \
  --concurrency 1,2,4,8 --tokens 16 --split 18
.venv/bin/python bench/publication_analyze.py results/laptop-main
```

This is **320 runs**: four setups × two contexts × four concurrency levels ×
ten repetitions. Each run serves four or eight requests and checks every
returned token sequence. Arm and condition order are randomized.

| Setup | What runs | Compute budget |
|---|---|---|
| Unsplit, one thread | Entire model on your laptop | One compute thread; other budget unused |
| Unsplit, two threads | Entire model on your laptop | Two compute threads on your laptop |
| Two full-model replicas | Entire model on each laptop; first available replica reserves each request | One compute thread per laptop |
| Two-stage pipeline | Layers 0–17 on your laptop, 18–27 on your friend's | One compute thread per laptop |

The total distributed compute-thread budget is two. Laptop CPU speeds can
still differ: two threads on your laptop are not identical physical resources
to one on each laptop. The manifest records hardware, packages and affinity.
The fixed 18/10 split is a declared baseline, not a claim of optimal placement
for your specific laptops. Record that qualification in the paper.

Primary measurements: whole-run tokens/s, client completion time, TTFT,
failures, exact token agreement, and worker queue/compute/residual timings.
The remaining residual contains serialization, scheduling and transport; it
must not be renamed pure Wi-Fi RTT. Requests within one run are not independent
experimental repetitions. The analyzer uses run-level repeated blocks.

If a run is interrupted, restart both agents, then repeat the same command
with **`--resume`** and the same output directory. It runs missing observations
only and rejects changed environments/arguments. Preserve all original files.

## 4. Additional output/context-length test

If there is time after the main matrix:

```bash
.venv/bin/python bench/lan_publication.py \
  --local http://192.168.1.10:56080 --peer http://192.168.1.20:56080 \
  --out results/laptop-longer --repetitions 10 --contexts 128,512 \
  --concurrency 1,4 --tokens 64 --split 18
.venv/bin/python bench/publication_analyze.py results/laptop-longer
```

This tests whether conclusions change for longer prefill and output. It is a
separate **160-run** matrix; keep it separate from the 320-run matrix. The
inputs are seeded token IDs, not a natural-language quality benchmark.

## 5. Recovery test on the two physical laptops

For each position **1, 4 and 12**, run this command, changing the position and
output folder each time:

```bash
.venv/bin/python bench/lan_publication.py \
  --local http://192.168.1.10:56080 --peer http://192.168.1.20:56080 \
  --out results/laptop-recovery-p4 --repetitions 3 --contexts 64 \
  --tokens 32 --recovery --position 4
.venv/bin/python bench/publication_analyze.py results/laptop-recovery-p4
```

The kit waits for observed output progress, stops the friend's owned worker,
loads the complete model on the survivor and publishes a new layout. Check:

- Final tokens exactly match the unsplit reference, without duplicates or omissions.
- The request resumes; save the actual observed fault position.
- Save `maximum_internal_token_gap_ms`, disruption and reconstruction durations.

This is **manual fault orchestration**, not automatic heartbeat detection.
Polling can overshoot the requested position; the observed remaining-token
snapshot is recorded. The HTTP response arrives after generation finishes;
internal token timestamps do not prove client streaming delivery. The survivor
must have enough memory for the complete model.

For automatic recovery, use the installed Shardwise application's **Invite
laptops / Join** flow. While generating an answer, stop the friend's worker
through the app, observe reassignment and continuation, then restore it. Save
screenshots and application logs. Record that the application demo uses
Qwen2.5-0.5B-Instruct, whereas the performance kit uses Qwen3-0.6B. A demo
screenshot is not comparative throughput evidence.

## 6. Optional tests that improve real-world breadth

| Test | How | Why it helps |
|---|---|---|
| Reverse laptop roles | Run the main command with `--local`/`--peer` swapped from the other laptop; use a new folder | Separates coordinator placement from hardware differences |
| Wi-Fi versus Ethernet | Repeat under each connection, with separate folders and recorded addresses | Measures actual transport conditions |
| Naturally unequal laptops | Use the two real CPU models; save their specs and keep settings fixed | Adds physical heterogeneity without inventing slowdown |
| Sustained operation | After warmup, repeat blocks over time with cooling/power settings recorded | Checks drift; do not claim thermal throttling without temperature evidence |

Run laptops on AC power. Finish downloads/updates before timed trials. Avoid
other benchmarks, gaming or large file transfers during measurements. Record
unavoidable interruptions rather than quietly deleting inconvenient runs.

## 7. What to send back

Send the **complete result folders** (`manifest.json`, `reference.json`,
`runs.jsonl`, `completion-status.json`, analysis JSON/CSV and `REPORT.md`), plus
the corresponding agent logs under `.lan-test-state/`. Include this small
metadata note for both laptops:

```text
Laptop A: OS/version, CPU, RAM, available WSL RAM if used, AC/battery, thread/affinity settings
Laptop B: OS/version, CPU, RAM, available WSL RAM if used, AC/battery, thread/affinity settings
Network: Wi-Fi/Ethernet, same router or other topology, distance, connection changes
Experiment: date/time, output folders, any interruptions/background activity
Demo: app version, screenshots, whether recovery was automatic or manual
```

Keep the raw data, even if the result is negative. Do not send the lab token,
model weights, `.venv`, or download caches. The paper can report physical
laptop results only after the actual data are collected and checked.
