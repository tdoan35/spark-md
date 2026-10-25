# 01: Box setup (partial — C-track prereqs validated Oct 24; rest not started)

Status: prereqs (C1) + iface/sudo notes validated on spark-2 Oct 24. Users, `$SPARKMD_HOME`, drive layout and venv are not written yet; the start/stop outline is below (unverified).
**Fresh-box dry run (E10) PASSED on spark-2, Oct 24 23:59** — as new user `sparkdry` (empty home, docker group only), egress blocked by owner-matched iptables, sourcing only byte-verified copies of the drive tars. Timings: weights-cache extract 10 s · offline kit 0 s · venv + 98-wheel `--no-index` install 39 s · import smoke 4 s (`torch 2.13.0+cu130`, CUDA `True`) · Lung-RADS suite pass · `docker load` TensorFold 34 s / sandbox 3 s · offline HF resolve from extracted cache OK. **Total 90 s.** Skipped: second-server start (live LLM holds the GPU; cache resolution + image load proven separately; A0 proves serving). Full script: `scripts/e10_dry_run.sh` + `/tmp/e10_sparkdry.sh` (spark-2).

## Purpose and scope

Brings a fresh GB10 (DGX OS / Ubuntu-class) from powered-on to "Docker + GPU + interfaces ready".

## Start-all, stop and status (outline, Oct 25 — **unverified; no script exists**)

Goal: one command takes the box from powered-on to a working worklist, in an order the pieces tolerate, and is safe to re-run. Written to `$SPARKMD_HOME/bin/sparkmd-{start,stop,status}` on the day. The cold-restart test (11, C1–C5) is what turns this outline into real lines: record each step that needed a manual fix.

| # | Step | Waits for | Failure |
| --- | --- | --- | --- |
| 0 | Export `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 NEMOCLAW_DISABLE_TELEMETRY=1 SPARKMD_HOME=…` | – | – |
| 1 | Preflight: `free -g`; stop if `MemAvailable` is low or an old container is half-running | – | fatal |
| 2 | Create `spark0` (`10.77.0.1/32`) if missing | `ip addr show spark0` | fatal; needs sudo at the console (a one-time systemd unit is the likely fix, unverified) |
| 3 | LLM: `HOST=0.0.0.0 PORT=8000 SERVED_NAME=qwen3.8-27b PARALLEL=4 CONTEXT=65536 KV_POOL_GB=16 PREPARE=0 ./start.sh` (02) | `/v1/models` answers (31–70 s) | fatal |
| 4 | Block `:8000` on external interfaces | rule present | warn, continue (method unverified) |
| 5 | OpenShell sandbox and gateway up | sandbox can `curl host.openshell.internal:8000/v1/models` | fatal |
| 6 | Worker on `10.77.0.1:8100` and loopback (06) | `/api/health` is 200 | fatal |
| 7 | Voice: `whisper-server :8178`, then TTS `:8020` | each answers | warn, continue (UI falls back to mute and clicks) |
| 8 | Electron UI | worklist loads | warn |

Rules for all three scripts:
- **Idempotent.** Each step checks "already up?" first (as `start.sh` does), so a re-run after a partial failure continues instead of restarting everything.
- **Timeouts and one-line results.** Every wait has a timeout and prints `OK` / `WARN` / `FAIL` with the step name.
- **No network and no downloads.** `PREPARE=0`, no image pulls, no `:latest` tags; a missing image or checkpoint fails fast.
- **Services only.** The script never starts a benchmark or a second heavy GPU job.
- **`stop` reverses the order** (UI, voice, worker, sandbox, LLM) and leaves `spark0`, the registry, `cache/` and `outbox/` alone. `status` prints the same table with live checks.

Unknowns the first reboot test must answer: whether the sandbox, its policy and the gateway survive a reboot or need re-onboarding; whether `spark0` can be recreated unattended without passwordless sudo; how to block `:8000` externally; the real total time (11 uses ≤ 5 min as a placeholder).

## Build steps → verification (measured on spark-2, Oct 24)

| Step | Command | Expected / got |
| --- | --- | --- |
| OS | `head -n2 /etc/os-release` | Ubuntu 24.04.5 LTS |
| Docker | `docker version --format "{{.Server.Version}}"` | ≥ 28 (29.6.2 measured) |
| GPU in containers | `docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu24.04 nvidia-smi` | GB10 listed (works via CDI, `/run/cdi/nvidia.yaml`) |
| Memory | `free -g` (`MemAvailable`) | ≥ 15 GiB floor with the full stack; 111 GiB free idle |

## Parameters

- Worker dummy interface (cable-pull-proof): `sudo ip link add spark0 type dummy && sudo ip addr add 10.77.0.1/32 dev spark0 && sudo ip link set spark0 up` — **unverified on GB10 (needs sudo at the console; spark-2 has no passwordless sudo)**. Zero-sudo fallback, also cable-pull-proof: docker0 `172.17.0.1` (validated as the worker address in C3).
- LLM bind: `HOST=0.0.0.0` so the OpenShell sandbox bridge (`host.openshell.internal` → `172.18.0.1:8000`) can reach it; block `:8000` on external interfaces (unverified how; iptables at the console).

## Event LAN (Mac ↔ box), planned Oct 25, **unverified**

Ty's unmanaged switch has no DHCP, so every host gets a static IP with **no gateway** (Wi-Fi keeps the default route and internet where there is any). `10.78.0.0/24` avoids `spark0` (10.77.0.1), Docker (172.17/18) and Tailscale (100.x).

| Host | IP | Set with |
| --- | --- | --- |
| tys-macbook-air | 10.78.0.2 | System Settings → Network → USB LAN adapter → TCP/IP: Manually, no router |
| Event box | 10.78.0.10 | `sudo nmcli con add type ethernet ifname <eth> con-name sparkmd-lan ipv4.method manual ipv4.addresses 10.78.0.10/24 ipv6.method disabled && sudo nmcli con up sparkmd-lan` |

- Check: `ping 10.78.0.10` from the Mac, then `ssh <user>@10.78.0.10`. Put the hosts in the Mac's `~/.ssh/config` so Remote-SSH works by name.
- If the box's port is already on venue DHCP, leave it alone and use the venue address, or add the static IP as a second address (`nmcli con mod <con> +ipv4.addresses 10.78.0.10/24`).
- The box LLM binds `0.0.0.0:8000` (above). On our own switch that's fine, but if the box joins venue Wi-Fi, firewall `:8000` there.
- The Mac has no Ethernet port: bring the USB-C adapter.

## Gotchas

- **Fresh-user rehearsal gotchas (hit Oct 24):** a new user cannot traverse `/home/<you>` (home dirs are `o-x`) — `sudo chmod o+x /home/<you>` or stage sources outside home; the user needs `usermod -aG docker <user>` before docker works; multi-line pastes wrap at the console — launch via a one-line `sudo bash <script>` launcher; `sudo -u <user>` from a non-tty ssh fails (no askpass) — launch detached from the console instead.
- Owner-matched egress block for the rehearsal: `sudo iptables -I OUTPUT -m owner --uid-owner <user> -j DROP`; **verify the auto-revert timer actually took the full rule** (a wrapped paste produced an invalid `iptables -D` that silently never reverts — check with `sudo iptables -S OUTPUT | grep <user>` and delete by hand).

## Open / unverified

- spark0 creation on the event box (sudo), external firewall for `:8000`, everything in L0. (C4 cable-pull rehearsal dropped Oct 24 — demos run fully local; spark0 is a dummy iface, so nothing here depends on the LAN link.) Second-server start from the extracted cache (E10 step skipped; cache resolve + docker load + A0 serving each proven individually). Venue time budget: tars → local NVMe copy is the dominant cost (~10–15 min for 74 GB via USB), the rebuild itself measured at 90 s.
