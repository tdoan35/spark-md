# agent/ — OpenShell + OpenClaw layer (spec: docs/build/07-agent.md)

Box-side, as `ty`, after R8 (NemoClaw onboard, sandbox `spark-md-openclaw`) and once the worker serves `/mcp`.
`NEMOCLAW_DISABLE_TELEMETRY=1` is set by `setup/env.sh`. Worker address defaults to `10.77.0.1:8100`
(`WORKER_HOST=172.17.0.1` if `spark0` is not up yet, 07 Gotcha 7).

| Order | Script | Implements |
| --- | --- | --- |
| 1 | `setup/10-policy-preset.sh` | 07 §Worker policy preset, enforce; Gotchas 3/4/6; GET+DELETE `/mcp` (C5 gotcha) |
| 2 | `setup/20-mcp-server.sh` | 07 §C5 wiring: MCP `spark-md-worker` → `http://$WORKER/mcp`, `requestTimeoutMs` 60000 |
| 3 | `setup/30-tools-profile.sh` | 00 §Agent tools: profile `minimal` + deny fs/runtime/web/messaging groups |
| 4 | `setup/40-skill.sh` | 07 §Confirm-flow update: `skill/AGENTS.md` → `/sandbox/.openclaw/workspace/AGENTS.md` |
| 5 | `setup/50-hooks.sh` | 06 step 6: hooks block (token generated on the box → `$SPARKMD_HOME/.env`), chatCompletions, gateway restart |
| 6 | `tests/acceptance.sh` | 07 §Acceptance tests + confirm-flow checks |

Unverified until run on the box: `openclaw config set` syntax for nested keys/arrays, the `tools.deny` group
names, whether `tools.profile minimal` hides MCP tools (A6 checks), `sandbox exec` passing long arguments.
