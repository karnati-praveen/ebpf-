# Shardwise laptop demo

Run real Qwen3-0.6B inference on Ubuntu using a CPU or a compatible NVIDIA GPU. Watch 28 model layers move between workers, stop one worker, and observe recovery. Solo runs independently on each laptop. Pair connects two trusted laptops. Splitting on one device demonstrates placement and recovery; it does not promise faster inference.

## Install

Use Ubuntu 22.04 or 24.04 on an x86_64 laptop. Download the release `.deb` and checksum, then open a terminal in that folder:

```bash
sha256sum -c shardwise_0.1.0_amd64.deb.sha256
sudo apt install ./shardwise_0.1.0_amd64.deb
shardwise solo
```

You can also open **Shardwise Demo** from the applications menu. The terminal prints a localhost browser URL. Keep the terminal open during the demo.

First launch downloads a managed Python 3.12 environment, pinned dependencies, and model assets. The measured CPU runtime uses about 1 GB, and the model cache uses about 1.5 GiB; reserve additional room for download caches. The installer is approximately 48 MiB. CUDA runtime size has not yet been measured and may be substantially larger. Internet is required for setup; subsequent launches reuse cached assets. Interrupted downloads can be resumed by running the same command again. The application does not install NVIDIA drivers.

From a source checkout, install Go and [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```bash
mkdir -p bin
go build -o bin/controller ./cmd/controller
go build -o bin/nodeagent ./cmd/nodeagent
SHARDWISE_BIN="$PWD/bin" demo/keinfer-demo solo
```

Build the installer with `packaging/build-deb.sh 0.1.0` after installing Go, curl, and dpkg build tools. The installer bundles uv, Go executables, and source files; Python is downloaded at first launch. No system Python or Go is needed on the receiving laptop.

## Solo quickstart

1. Run `shardwise solo` and open the printed URL.
2. Wait through downloading, calibration, and loading. Device **Auto** tests CUDA and falls back to CPU if needed.
3. Ask a short question. Each answer reports real timing and token counts.
4. Inspect the two coloured layer bars. Layer ranges are half-open internally: `[0,14]` represents layers 0–13.
5. Stop one worker. Watch the survivor receive all 28 layers, then restore the worker.

Two CPU workers require at least 11 GB free RAM; CUDA requires approximately 3 GB free VRAM per worker. These are startup checks, not guarantees of peak memory. An 8 GB laptop normally starts one worker, with recovery controls disabled and a reason displayed. Chat still works. Switching the device restarts the pipeline and may recalibrate.

`shardwise status` reports the running application; `shardwise stop` stops its own processes and clears its active faults.

## Pair quickstart

Use a trusted shared Wi-Fi network; a phone hotspot is convenient. On the host:

```bash
shardwise host
```

Copy the printed join command and token into the friend's terminal:

```bash
shardwise join HOST_IP TOKEN
```

The host browser provides chat and pipeline controls. The friend's browser reports its local worker and real hardware; send chat from the host. Each laptop selects its own available CPU/CUDA device. The host supplies a shared reference profile for placement normalization; per-device calibration remains separate. Mixed CPU/GPU Pair inference has not yet been validated on physical NVIDIA hardware. Restart Pair to change devices; the dashboard device selector is available only in Solo. Each laptop needs enough memory for its worker, including holding all layers during recovery.

The host enrollment port is TCP 8766. Controller, worker, and helper ports are dynamically assigned and printed during startup. Permit those actual ports between the two laptop IPs on the trusted network. Do not expose them to the internet; the session uses authenticated control but is not a public TLS service. Corporate Wi-Fi may isolate clients; try a phone hotspot if the laptops cannot reach one another.

Pair fault buttons appear only when supported. **Slow down** pauses only the demo worker. **100 ms transport delay** delays the application's worker transport relay; it does not change the laptop's network configuration. **Clear faults** removes both effects. These are application-level fault demonstrations, not kernel netem or eBPF benchmarks.

## Five-minute presentation

- **0:00–1:00:** Show device selection and genuine CPU/RAM or GPU/VRAM readings. Explain Solo versus Pair.
- **1:00–2:00:** Ask “Explain distributed inference in three sentences.” Point to generated text and measured timings.
- **2:00–3:00:** Click the layer bars and explain that the workers together hold 28 layers.
- **3:00–4:00:** Stop a worker, observe the recovering state, and show all layers assigned to the survivor. Ask another question when ready.
- **4:00–5:00:** Restore it, show the returned split and controller event log. In Pair, optionally demonstrate an available slow/transport fault and clear it.

## Troubleshooting

- **Setup interrupted:** rerun the launcher. Run `demo/runtime-setup.sh cpu` from a checkout to prepare CPU dependencies explicitly.
- **No NVIDIA GPU or incompatible driver:** Auto uses CPU and shows a reason. Force GPU reports an error. Check `nvidia-smi`; install a suitable driver through Ubuntu's normal driver tooling if needed.
- **One worker only:** close other memory-heavy programs; restart. Do not expect two workers on every 8 GB laptop.
- **Port or duplicate instance:** the application selects free local ports. Use `shardwise status` and `shardwise stop` before relaunching. Pair enrollment on 8766 must be available.
- **Pair cannot connect:** verify host IP, token, firewall, and Wi-Fi client isolation. Check the startup terminal for actual ports.
- **Backend unreachable:** the UI keeps reconnecting. Inspect the terminal and logs under `~/.local/share/shardwise/logs`.
- **Input too long:** shorten the conversation to fit the 512-token context, including the requested output budget. Start a fresh browser conversation if needed.

## Is it safe for my friend's laptop?

The package installs under `/opt/shardwise`, with its application entry and launcher under `/usr`. Managed Python, dependency caches, profiles, model cache, logs, and state live under `~/.local/share/shardwise`. You can override that directory with `SHARDWISE_HOME` (the older `KEINFER_DEMO_HOME` alias also works; `SHARDWISE_HOME` takes precedence). The `keinfer-demo` command remains a compatibility alias.

The demo runtime is rootless. Sudo is used for package installation/removal only; this application does not load privileged eBPF programs, change drivers, or change system network queues. Faults affect only its worker processes/transport. `shardwise stop` clears faults and stops application-owned processes. Existing research services are separate.

Stop as the user who launched it **before uninstalling**:

```bash
shardwise stop
sudo apt remove shardwise
```

Uninstall intentionally preserves your downloaded models and runtime. To remove them permanently, after stopping the app:

```bash
rm -rf -- "$HOME/.local/share/shardwise"
```

Use the corresponding directory if you set `SHARDWISE_HOME`.

## UI-only development

`python3 demo/mock_api.py` serves fake inference and hardware for UI testing. Add `--gpu`, `--single-worker`, or `--mode host`. It is labelled as simulated and excluded from the installer. Production hardware panels never manufacture missing readings; they show `n/a`.
