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

Reopen Ubuntu. Mirrored networking gives Ubuntu the same network address as Windows, so other laptops can reach it.

**Joining needs none of this.** A Windows laptop that only *joins* another laptop's invite works in WSL's default NAT mode (Windows 10 too) with no firewall change, because joined laptops make only outgoing connections. Mirrored networking and the firewall rules below are needed only on the laptop that **invites**. Without them, the dashboard's **Connect more laptops** card shows a warning instead of an address that cannot work. If you can, let a native-Ubuntu laptop do the inviting.

Inviting uses the fixed TCP ports **8766–8768**. On the **inviting** laptop only, in an **administrator** PowerShell, allow them through the Windows firewall and through the Hyper-V firewall that sits in front of WSL:

```powershell
New-NetFirewallRule -DisplayName "Shardwise Pair" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8766,8767,8768 -Profile Private
New-NetFirewallHyperVRule -Name ShardwisePair -DisplayName "Shardwise Pair" -Direction Inbound -VMCreatorId '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' -Protocol TCP -LocalPorts 8766,8767,8768
```

Mark the Wi-Fi as a **Private** network in Windows settings (public networks block inbound connections). A phone hotspot is the most reliable choice at a venue; university and guest Wi-Fi often block laptop-to-laptop traffic.

Remove both rules after the presentation if you like:

```powershell
Remove-NetFirewallRule -DisplayName "Shardwise Pair"
Remove-NetFirewallHyperVRule -Name ShardwisePair
```

## NVIDIA GPU

Install/update the normal **Windows NVIDIA driver** (a driver that reports `CUDA Version: 13.0` or newer in `nvidia-smi`; with an older driver Shardwise uses the CPU instead of downloading a GPU runtime that cannot run). The driver is exposed to Ubuntu; do not install a Linux NVIDIA display driver inside WSL. The app downloads its CUDA-enabled Python packages, probes the device, and selects CPU when CUDA cannot run. Check `nvidia-smi` inside Ubuntu. AMD/Intel GPU acceleration is not included in this version.

## Limitations

Shardwise opens the dashboard in your Windows browser automatically; if it does not, open the printed `http://127.0.0.1:…` URL in any Windows browser. Kernel eBPF and netem support varies between WSL kernels. This demo uses rootless worker pauses and a delay in its own worker tunnel, so its Pair controls do not depend on those kernel features. Unsupported controls are hidden. Neither transport-delay nor worker-pause faults establish performance of privileged kernel fault injection.

Official references: [WSL installation](https://learn.microsoft.com/windows/wsl/install), [WSL configuration](https://learn.microsoft.com/windows/wsl/wsl-config), [WSL networking/firewall](https://learn.microsoft.com/windows/wsl/networking), [NVIDIA CUDA on WSL](https://docs.nvidia.com/cuda/wsl-user-guide/index.html).
