You are helping me install and run **Shardwise**, a demo app that runs a small AI model (Qwen2.5-0.5B-Instruct) and can split it across several laptops. Guide me **one step at a time**. After each step, wait for me to paste the output or confirm before you continue. Run commands yourself if you have a terminal; otherwise give me the exact command to copy. Keep explanations short. I am not a Linux expert.

## Facts about the app (trust these, do not guess other values)
- Installer (Ubuntu/WSL x86_64 only): https://github.com/karnati-praveen/ebpf-/releases/download/shardwise-latest/shardwise_amd64.deb
- After install, the command is `shardwise`. Subcommands: `shardwise` / `shardwise solo` (start), `shardwise status`, `shardwise stop`, `shardwise host` (invite from the terminal), `shardwise join HOST_IP CODE`.
- The first run downloads Python, its packages and the model (about 2–3 GB in total, once). It needs internet. Keep the terminal open; it prints a `http://127.0.0.1:...` dashboard URL to open in a browser.
- Data lives in `~/.local/share/shardwise` (logs in `~/.local/share/shardwise/logs`). The app itself is in `/opt/shardwise`.
- Needs about 3 GB free RAM for one worker and 7 GB free for two workers on one laptop. With less it runs one worker; chat still works.
- An NVIDIA GPU is used automatically if the driver works; otherwise it uses the CPU. Never install or change GPU drivers for this.
- **Multiple laptops:** all laptops on the same Wi-Fi (a phone hotspot works best; college or guest Wi-Fi often blocks laptop-to-laptop traffic).
  - ONE laptop clicks **Invite laptops** in the dashboard. It shows an address and an 8-digit code.
  - Every other laptop types those into **Join a laptop** and clicks Join. Up to 15 laptops can join.
  - Only the inviting laptop needs incoming TCP ports **8766–8768** open. Joining laptops need no firewall change.

## Steps
1. **Detect my system.** Run `uname -m; cat /etc/os-release | head -3; free -h; nproc; nvidia-smi -L 2>/dev/null || echo no-gpu`. Tell me if I am on Windows, macOS or Linux. If you cannot tell, ask me.
   - **Windows:** set up WSL2 Ubuntu first. In an *administrator* PowerShell, run `wsl --install -d Ubuntu`, restart if asked, open "Ubuntu" from the Start menu and create a username and password. Do every later step **inside Ubuntu**.
     - Only if this Windows laptop will be the *inviting* laptop, on Windows 11 22H2 or newer:
       - Create `%USERPROFILE%\.wslconfig` containing `[wsl2]`, `networkingMode=mirrored` and `memory=8GB`. Adjust the memory to fit the laptop.
       - Run `wsl --shutdown` and reopen Ubuntu.
       - In an admin PowerShell, run:
         `New-NetFirewallRule -DisplayName "Shardwise Pair" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8766,8767,8768 -Profile Private`
         `New-NetFirewallHyperVRule -Name ShardwisePair -DisplayName "Shardwise Pair" -Direction Inbound -VMCreatorId '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' -Protocol TCP -LocalPorts 8766,8767,8768`
       - Set the Wi-Fi to a **Private** network.
       - Otherwise, a Windows laptop should just *join* and needs none of this.
   - **macOS, or ARM (aarch64) Linux:** stop and tell me this .deb will not run here. Suggest using this laptop only as a viewer, or another laptop.
   - **Ubuntu 22.04/24.04 x86_64** (native or WSL): continue.
2. **Download and install:**
   ```bash
   cd ~ && curl -fL -o shardwise_amd64.deb https://github.com/karnati-praveen/ebpf-/releases/download/shardwise-latest/shardwise_amd64.deb
   sudo apt update && sudo apt install -y ./shardwise_amd64.deb
   ```
   If `apt` complains about dependencies, run `sudo apt -f install`. Confirm with `which shardwise`.
3. **Start it:** `shardwise`. Wait for it to print the URL. Open that URL in the browser (in WSL, a Windows browser works). Explain the progress states while it runs: downloading, then calibrating, then loading, then ready. If it is interrupted, simply run `shardwise` again; it resumes.
4. **Solo test:** in the dashboard, ask a short question, then look at the layer bars. If there are two workers, click **Stop** on one, watch the other take all 24 layers, then **Restore** it.
5. **Multiple laptops (optional):** ask me whether this laptop will **invite** or **join**.
   - **Invite** (native Ubuntu preferred): run `sudo ufw status`. If ufw is active, run `sudo ufw allow 8766:8768/tcp`. Then click **Invite laptops** and tell me to share the address and code.
   - **Join:** type the address and code into **Join a laptop** and click Join. The terminal alternative is `shardwise join ADDRESS CODE`.
   - If joining fails, read the message:
     - **wrong code:** re-check the code;
     - **refused:** the other laptop is not inviting, or the address is wrong;
     - **no answer:** a different network, Wi-Fi client isolation, or the inviting laptop's firewall. Switch to a phone hotspot.
6. **Problems:**
   - Run `shardwise status`.
   - Show the last lines of the newest log: `ls -t ~/.local/share/shardwise/logs | head`, then `tail -50` that file.
   - Fix the problem from what you see.
   - "Already running" or a stuck state: run `shardwise stop`, then `shardwise`.
   - Low RAM: close browsers and other heavy apps, then restart.
7. **Finish:** `shardwise stop`.
   - To uninstall later, run `sudo apt remove shardwise`.
   - To also delete the downloaded model and runtime, run `rm -rf ~/.local/share/shardwise`.

Rules: never run commands that change drivers, delete files outside `~/.local/share/shardwise` and `~/shardwise_amd64.deb`, or open ports other than 8766–8768. Ask me before any `sudo` command other than those listed above.

Start now with step 1.
