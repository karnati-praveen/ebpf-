# Run the demo on Windows with Ubuntu in WSL2

Use a recent Windows installation with WSL2. In an administrator PowerShell terminal:

```powershell
wsl --install -d Ubuntu
```

Restart if prompted, open Ubuntu, and create your Linux username/password. Follow [the Ubuntu installation instructions](README.md) inside Ubuntu. The Linux `.deb` is installed inside WSL; it is not a Windows installer.

## Pair networking and memory

On **Windows 11 22H2 or later**, create `%USERPROFILE%\.wslconfig` with:

```ini
[wsl2]
networkingMode=mirrored
memory=12GB
```

Choose a memory limit your physical laptop can support; a 12 GB limit does not create additional RAM. Two CPU workers still require 11 GB **free** RAM inside WSL. An 8 GB physical laptop should use one worker.

Then run:

```powershell
wsl --shutdown
```

Reopen Ubuntu. Mirrored networking helps the host and friend reach services across the LAN. Enrollment uses TCP 8766, while controller/worker/helper ports are dynamically printed. Replace `8766,12345,12346` below with the actual ports for your role, and `192.168.1.42` with the friend's IP:

```powershell
New-NetFirewallRule -DisplayName "Shardwise Pair" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8766,12345,12346 -RemoteAddress 192.168.1.42 -Profile Private
```

WSL's Hyper-V firewall can also filter mirrored traffic. If connections remain blocked, add equivalent narrowly scoped rules for the WSL VM through your Windows firewall settings. Use a private trusted hotspot/network. Windows 10 does not support mirrored mode; use native Ubuntu or configure WSL forwarding separately for Pair.

Remove your rule after the presentation if desired:

```powershell
Remove-NetFirewallRule -DisplayName "Shardwise Pair"
```

## NVIDIA GPU

Install/update the normal **Windows NVIDIA driver supporting WSL CUDA**. The driver is exposed to Ubuntu; do not install a Linux NVIDIA display driver inside WSL. The app downloads its CUDA-enabled Python packages, probes the device, and selects CPU when CUDA cannot run. Check `nvidia-smi` inside Ubuntu. AMD/Intel GPU acceleration is not included in this version.

## Limitations

The browser UI is on localhost; use the printed URL in your Windows browser. Kernel eBPF and netem support varies between WSL kernels. This demo uses rootless worker pauses and an application transport-delay relay, so its Pair controls do not depend on those kernel features. Unsupported controls are hidden. Neither transport-delay nor worker-pause faults establish performance of privileged kernel fault injection.

Official references: [WSL installation](https://learn.microsoft.com/windows/wsl/install), [WSL configuration](https://learn.microsoft.com/windows/wsl/wsl-config), [WSL networking/firewall](https://learn.microsoft.com/windows/wsl/networking), [NVIDIA CUDA on WSL](https://docs.nvidia.com/cuda/wsl-user-guide/index.html).
