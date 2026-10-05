# Shardwise implementation and validation

Verified on 2026-10-05. Backend and UI/packaging work were split between two agents, then integrated on `demo/laptop-app`. The UI branch is `demo/laptop-app-ui`. The original checkout and all seven existing edited/untracked files were left unchanged, verified by SHA-256 comparison.

## Artifact

- Ubuntu amd64 package: `dist/shardwise_0.1.0_amd64.deb`, 50,437,562 bytes (48.1 MiB).
- SHA-256: `6b122c0548f266e46a6a52a042fc6d62432db338204c5d0d1b53373374a78744`.
- Clean Ubuntu CPU runtime: 973 MiB, plus 107 MiB managed Python. Cached model: approximately 1.5 GiB; allow extra disk space for download caches.
- Qwen3-0.6B snapshot: `c1899de289a04d12100db370d81485cdf75e47ca`.
- `packaging/verify-deb.sh` checks identity, canonical launcher, exact 0755 executable permissions and exclusion of development mocks/tests/bytecode.

## Passed checks

- `go test ./...`.
- Four existing worker Python tests and ten demo/router tests, including optional EOS stopping compatibility, device selection and readiness/crash handling.
- Python compilation, shell syntax, and `git diff --check`.
- Playwright/Chromium UI suite: CPU and mock GPU, Solo/Pair/Join/single-worker states, light/dark, projector/phone widths, startup/reconnection, chat/error handling, load/fault controls, all 28 layers, walkthrough and exit. No JavaScript errors or horizontal overflow. Mock GPU verifies rendering only.
- Real CPU Solo: actual model inference, 18/10 initial split, in-flight worker loss with token replay, survivor assigned `[0,28)`, real post-recovery inference, and worker restoration. Concurrent chat returns 409; invalid auth 403; oversized context and last-worker stop are refused. Background load uses real inference.
- `bench/verify_qwen3.py --relayout --tokens 32`: MATCH and RELAYOUT OK, three replays, matching tokens before/after a layout change at the same CPU precision.
- Local two-instance Pair: independent app homes, real split inference, friend-worker stop/recovery/restore, scoped process slowdown and application transport delay, clear faults, and clean shutdown of both instances. This test used loopback, not two physical laptops.
- Package installation, bundled controller execution and complete managed Python 3.12 CPU setup/imports in fresh Ubuntu 22.04 and 24.04 Docker images. No preinstalled runtime or development toolchain was needed.
- Installed app run as an ordinary user on both Ubuntu versions: offline cached-model launch, duplicate-launch rejection, POST authentication, real chat, worker-stop recovery to all 28 layers, post-recovery chat, restoration to two workers, and `shardwise stop` completing with no owned worker/controller/router processes left.
- Force GPU without NVIDIA fails before runtime downloads. CPU-only operation and automatic CPU fallback were verified; GPU capability and rendering have separate tests.

## Implementation decisions

The requested base branch `research/phase0-1-measurement` was unavailable locally. Both isolated worktrees were created from existing commit `c0dea08`, without altering the user's checkout. The existing standalone scripts use privileged setup and broad cleanup, so the demo starts equivalent components directly, with scoped process ownership and rootless application measurements. This preserves the research workflow.

The calibration script supports `--device`, so that option replaces the plan's nonexistent `--env`. Layers use half-open ranges `[0,28)`; the mock's proposed `[0,27]` endpoint was corrected. Unknown download progress remains null; the UI shows the current phase instead of inventing a percentage.

Shardwise uses canonical `shardwise`, `SHARDWISE_HOME`, `/opt/shardwise` and `~/.local/share/shardwise` names. Older KEINFER environment variables and command remain compatibility aliases. Pair network faults use a scoped application TCP relay, not kernel netem. Demo eBPF loading is disabled; existing research eBPF code is unchanged. Pair device changes require restarting Pair.

## Remaining hardware validation

Actual NVIDIA inference, mixed CPU/GPU Pair, physical Wi-Fi between two laptops, and Windows/WSL were not exercised in this environment. Ubuntu tests share the host kernel through Docker. CPU/GPU memory checks determine one versus two workers; two workers are not guaranteed on every laptop. CUDA runtime disk usage is unmeasured. No external connector plugin is required for this local application.

Azure VMs were not accessed, honoring the plan's explicit restriction. Two local instances were used for Pair validation instead.
