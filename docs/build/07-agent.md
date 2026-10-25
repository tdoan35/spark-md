# 07: Agent — OpenShell + harness (C-track findings, Oct 24)

Status: **C1–C3 + C5 validated on spark-2 (Oct 24)**; harness = OpenClaw (bake-off curtailed for time: Hermes and custom-loop not run). C4 cable-pull rehearsal dropped Oct 24 (rules: demos run fully local on the event box); sandbox → worker is C3-proven.
Rebuild budget on the day: ~15 min install + ~4 min onboard (measured; sandbox image build ~2 min with the image cached — cold build unverified).

## Purpose and scope

Installs OpenShell + NemoClaw and an OpenClaw sandbox on the event box, wires it to the local LLM and the imaging worker (MCP), and locks it down with an enforce-mode network policy. Includes the C5 bake-off result.

## Interfaces

- Sandbox name: `spark-md-openclaw` (OpenClaw agent; harness decision pending C6).
- Inference from inside the sandbox: `http://host.openshell.internal:8000/v1` (sandbox `/etc/hosts` maps it to the sandbox bridge `172.18.0.1`). Model `qwen3.8-27b`.
- Worker from inside the sandbox: `http://172.17.0.1:8100` (docker0 gateway; swap to `10.77.0.1` on `spark0` — one sudo command, see Gotchas).
- Dashboard: `http://127.0.0.1:18789/` (host; `ssh -L 18789:127.0.0.1:18789` to view remotely).
- Egress path for ALL sandbox traffic: HTTP proxy `http://10.200.0.1:3128` (injected env `http_proxy/https_proxy/grpc_proxy/ALL_PROXY`), which is the policy enforcement point.

## Dependencies (versions measured Oct 24, spark-2)

| Component | Version | Source |
| --- | --- | --- |
| Node.js | v22.23.4 (npm 10.9.9) | nvm (installed by NemoClaw installer) |
| nemoclaw CLI | v0.0.137 | installer, ref `lkg` → commit `f00fb1dafe2113940b89bcd82f0561adf2696a7b` |
| openshell CLI + gateway | 0.0.116 | installer (binary tarball, aarch64-musl) |
| OpenClaw (in sandbox) | 2026.9.2 (3928bad) | pulled by installer |
| Gateway service | `~/.config/systemd/user/nemoclaw-openshell-gateway.service` | listens `127.0.0.1:8080` + `172.18.0.1:8080` |
| Sandbox image | untagged build, sha256 `79c25185417a…` | built at onboard |

Docker-image diff across install+onboard: **only** `nvidia/cuda:12.8.0-base-ubuntu24.04` (that was our C1 GPU probe, not the installer). The sandbox image is an untagged local build; capture for the offline kit via `docker save <sha>` (E6).

## Build steps (exact commands, run as `ty`, telemetry off)

```bash
export PATH="$HOME/.local/bin:$PATH" NEMOCLAW_DISABLE_TELEMETRY=1
# 1. install (75 s measured; pulls Node via nvm + OpenShell + builds the CLI)
NEMOCLAW_NO_EXPRESS=1 NEMOCLAW_NON_INTERACTIVE=1 \
  NEMOCLAW_ACCEPT_THIRD_PARTY_SOFTWARE=1 bash nemoclaw-installer.sh
# 2. onboard (42 s measured with image cached; ~2 min first sandbox build)
NEMOCLAW_NON_INTERACTIVE=1 NEMOCLAW_AGENT=openclaw \
  NEMOCLAW_SANDBOX_NAME=spark-md-openclaw NEMOCLAW_POLICY_TIER=restricted \
  NEMOCLAW_POLICY_MODE=suggested NEMOCLAW_PROVIDER=vllm \
  NEMOCLAW_MODEL=qwen3.8-27b nemoclaw onboard --fresh --name spark-md-openclaw
```

Verification (all measured passing Oct 24):

```bash
openshell sandbox exec -n spark-md-openclaw -- curl -s http://host.openshell.internal:8000/v1/models
# → {"object":"list","data":[{"id":"qwen3.8-27b",...}]}
```

## Parameters

- `NEMOCLAW_PROVIDER=vllm` → provider `vllm-local` = "standalone vLLM on `localhost:${NEMOCLAW_VLLM_PORT:-8000}`". The gateway probes `localhost:8000/v1` from the host, then derives a sandbox-attached native provider (`_provider_nemoclaw_local_v1_<hash>`) allowing only `host.openshell.internal:8000` for the openclaw/node binaries.
- `NEMOCLAW_POLICY_TIER=restricted` (enum: restricted|balanced|open|personal). Restricted suppresses `openclaw-pricing` / `openclaw-diagnostics-otel-local` presets (fine for us).
- Env vars found in the real installer (the handoff's guesses corrected): `NEMOCLAW_ENDPOINT_URL` + `NEMOCLAW_PROVIDER_KEY` (custom provider), `NEMOCLAW_POLICY_TIER`, `NEMOCLAW_POLICY_MODE`, `NEMOCLAW_VLLM_PORT`, `NEMOCLAW_INSTALL_TAG`.

## Gotchas (each cost us a debug cycle today)

1. **`NEMOCLAW_PROVIDER=custom` is broken for local endpoints.** It registers `compatible-endpoint`, rewrites `localhost` → `host.openshell.internal`, and the sandbox smoke through `https://inference.local` dies `503 {"error":"inference service unavailable"}` (sandbox-scoped `GetInferenceRoute` NOT_FOUND; static credential withheld: "unbound static provider credential from binding-capable supervisor"). Fresh onboard, provider/route resets, `127.0.0.1` instead of `localhost`, auth headers — none fixed it. Use `vllm` + a server that answers on the bridge IP.
2. **The LLM must bind more than 127.0.0.1.** Native inference from the sandbox targets `172.18.0.1:8000` (bridge). Serve TensorFold with `HOST=0.0.0.0` (start.sh handles it; host clients keep using `127.0.0.1:8000`). 0.0.0.0 also exposes the keyless API on LAN/Wifi — on the event box, block `:8000` on external ifaces or bind `10.77.0.1` + `127.0.0.1` (two instances or a port-sharing shim; unverified). Warm restart measured 31 s.
3. **Policy rules without `--binary` match nothing.** `policy update --add-endpoint … --add-allow …` silently produces a preset no binary can use → even allowed routes 403. Always pass `--binary /usr/bin/curl --binary /usr/local/bin/node --binary /usr/local/bin/openclaw` (curl for tests).
4. **`--add-endpoint` with an access preset (`read-write`) expands to broad `METHOD /**` rules.** Rules from a second update replace them (explicit rules win, incoming preset ignored). Final state should list only your explicit method/path rules — verify with `policy get --full -o json`.
5. **Changing provider settings after onboard:** partial resumes skip cached steps and fail with "Cannot change provider '…' while recreating the published sandbox". Clean reset: `nemoclaw <name> destroy --yes --cleanup-gateway` + `openshell inference delete` + `openshell provider delete <name>`, then onboard `--fresh`.
6. **OpenShell's own cloud presets** (`clawhub`, `npm_registry`, `nvidia`, `openclaw_api`, `openclaw_docs`) are installed by default. Removed via `policy update --remove-rule <name>` each (measured; keep `_provider_*` and `managed_inference` — they are the LLM route).
7. **No passwordless sudo on spark-2.** `spark0` dummy-iface creation needs Ty at the console (event box: L0 in `01-box-setup.md`). The C4 cable-pull rehearsal is dropped (Oct 24): demos run fully local on the event box, and C3 covers sandbox → worker. `docker0` `172.17.0.1` works as a zero-sudo, cable-pull-proof worker address for testing.
8. GPU into containers: `--gpus all` only; there is **no** registered `nvidia` runtime (no `/etc/docker/daemon.json` on DGX OS). `--runtime=nvidia` fails.

## Worker policy preset (validated commands)

```bash
openshell policy update spark-md-openclaw \
  --add-endpoint 172.17.0.1:8100:read-write:rest:enforce \
  --binary /usr/bin/curl --binary /usr/local/bin/node --binary /usr/local/bin/openclaw \
  --add-allow '172.17.0.1:8100:GET:/api/**' \
  --add-allow '172.17.0.1:8100:POST:/api/studies/*/select-series' \
  --add-allow '172.17.0.1:8100:POST:/api/studies/*/analyze' \
  --add-allow '172.17.0.1:8100:POST:/api/studies/*/reports' \
  --add-allow '172.17.0.1:8100:POST:/api/studies/*/priority' \
  --add-allow '172.17.0.1:8100:POST:/api/viewer/command' \
  --add-allow '172.17.0.1:8100:POST:/api/agent-log' \
  --add-allow '172.17.0.1:8100:POST:/mcp' --wait
# swap 172.17.0.1 → 10.77.0.1 when spark0 exists
```

## Acceptance tests (measured passing, Oct 24, spark-2)

| Test | Command (inside sandbox) | Expected | Got |
| --- | --- | --- | --- |
| LLM models | `curl http://host.openshell.internal:8000/v1/models` | 200, `qwen3.8-27b` | 200 ✓ |
| LLM chat | POST `/v1/chat/completions` | completion | ✓ (thinking on by default) |
| Worker health | `curl http://172.17.0.1:8100/api/health` | 200 `{"status":"ok"}` | 200 ✓ |
| Worker POST | POST `/api/agent-log` | 200 | 200 ✓ |
| **Approve blocked** | POST `/api/reports/1/approve` | 403 `policy_denied` | 403 ✓ |
| Unlisted path | GET `/admin` | 403 `policy_denied` | 403 ✓ |
| Internet | `curl https://example.com` | denied | 000 ✓ |
| npm | `curl https://registry.npmjs.org` | denied | 000 ✓ |
| Denial visibility | `openshell logs spark-md-openclaw` | denied actions reported | `denied_action_count=2` activity summary ✓ |

## Measured performance (spark-2, Oct 24)

- Installer: 75 s (Node via nvm + CLI build + OpenShell). Onboard: 42 s (image cached); sandbox image build ~2 min inside that on first run.
- TensorFold warm restart (0.0.0.0 rebind): 31 s to ready.

## C5 bake-off result (Oct 24, OpenClaw only — curtailed for time)

Wiring: fixture worker (`bench/fixture_worker.py`, stdlib, v0 routes + MCP `/mcp`) on `0.0.0.0:8100`; OpenClaw MCP server `spark-md-worker` (`openclaw mcp add spark-md-worker --transport streamable-http --url http://172.17.0.1:8100/mcp`), 9 tools probed OK; triage skill at `/sandbox/.openclaw/workspace/AGENTS.md`; chat via gateway `chatCompletions` (enable with `openclaw config patch` `gateway.http.endpoints.chatCompletions.enabled=true`, then `nemoclaw <name> gateway restart`), `POST http://127.0.0.1:18789/v1/chat/completions`, model `"openclaw"`, token `nemoclaw <name> gateway-token --quiet`. Runner: `bench/c5_scenarios.py`. Raw: `docs/benchmarks/2026-10-24-c5-openclaw.raw.json` + `-requests.jsonl`.

| Gate | Result |
| --- | --- |
| Tool scenarios | **20/20** (gate ≥19/20); median 28.5 s, min 20.6, max 84.6 s |
| Triage flow | **5/5** complete 9-step chains (get_study → select_series → run_analysis → get_findings → log_event → save_report(radiology) → save_report(pcp_letter) → set_priority(elevated) → log_event); median 74.2 s/study (61–96 s) |
| Grounding | every radiology draft carries Lung-RADS **"4B" verbatim** + 14 mm / 47 d VDT / 371 d from the findings payload |

C5 gotchas: the MCP client also issues `DELETE /mcp` (session teardown) and `GET /mcp` (optional SSE channel — worker answers 405 per spec); both need policy allow rules or every connect logs a 403. Gateway tokens are short-lived — mint per run (`gateway-token --quiet`). Prefill dominates: **~60k-token system prompt per fresh session ⇒ ~30-35 s before first token** on TensorFold (no prefix reuse); keep sessions warm in the demo.

## Confirm-flow update (Oct 25, with 00 v0.6): two-phase triage — **unverified**

The C5 chain above was measured on the old flow (one run, straight to reports). With radiologist-confirmed diameters, triage is two agent runs per study:

| Phase | Trigger | Chain | Rules |
| --- | --- | --- | --- |
| 1 | new study (`POST /hooks/agent`, `Idempotency-Key: study-<uid>`) | `get_study` → `select_series` → `run_analysis` (returns `awaiting_confirmation`) → `get_findings` → `log_event` ("N nodule(s) await radiologist confirmation", lobe names only) | **No sizes, no category, no report, no priority.** Do not quote `proposal.*` numbers; they are for the radiologist, and the agent never proposes a diameter. |
| 2 | worker, after the last nodule is confirmed (`Idempotency-Key: study-<uid>-confirmed`) | `get_findings` → `log_event` → `save_report(radiology)` → `save_report(pcp_letter)` → `set_priority` (if elevated) → `log_event` | Every number from the confirmed findings; category verbatim from `assessment.lung_rads`. |

- **Skill text:** update `/sandbox/.openclaw/workspace/AGENTS.md` (the triage skill) with both phases, the "no numbers before confirmation" rule, and: if `assessment` is null, do not draft a report, log that confirmation is pending and stop. Phase 2 must refuse to proceed if findings still show `pending_confirmation`.
- **Warm session:** send phase 2 to the same OpenClaw session as phase 1 (same session key per study) to avoid a second ~30 s cold prefill. **Whether the hook API accepts a session key, and whether the first-turn prefix then helps on TensorFold (no prefix reuse), is unverified.** If not, expect ~30–35 s extra before report drafts appear after the Confirm click; plan the demo narration around it.
- **Policy: unchanged.** `POST /api/nodules/*/confirm` is not in the allow-list, so enforce mode already denies it (same mechanism as approve). Add the acceptance test below.
- No new tools: the agent still has no confirm or approve tool.

Acceptance tests to add (not run): `POST /api/nodules/1/confirm` from the sandbox → 403 `policy_denied`; a phase-1 transcript contains no millimetre values and no Lung-RADS category; a phase-2 draft's category and numbers all appear in the confirmed findings; re-run of C5's 5 triage flows against the two-phase worker (target ≥ 5/5, report median per phase).

## Open / unverified
- **Priority rule (ours, Ty Oct 25):** phase 2 calls `set_priority(elevated)` when `assessment.lung_rads` starts with "4" (4A/4B/4X); otherwise no priority call. Our rule, not ACR wording; the agent only string-matches the code-assigned category. Skill: event repo `agent/skill/AGENTS.md`.
- `/api/ask` (event repo `sparkmd/ask.py`): one session per study via the OpenAI `user` field (`spark-md-ask-<uid>`) on the gateway chatCompletions endpoint — **unverified** that OpenClaw keys sessions on it. Stub tests pass on the Mac (`tests/ask/test_ask.py`, 6/6, Oct 25).
- Hermes (H2) and custom-loop (H3) harnesses: **not run** — bake-off curtailed for time; OpenClaw chosen as NVIDIA's reference stack having passed all gates. Reopen only if OpenClaw blocks us.
- Sandbox cold build time (image not cached), offline install (E6 kit), `openshell term` TUI view of denials (logs API verified instead).
- Whether removing the cloud presets breaks any OpenClaw runtime feature that expects clawhub (not observed).
