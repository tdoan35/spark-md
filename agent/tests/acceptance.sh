#!/usr/bin/env bash
# 07 §Acceptance tests + §Confirm-flow update checks, run from the box host against the live sandbox.
# Usage: agent/tests/acceptance.sh [--with-llm]   (--with-llm adds A12/A13, which start agent runs)
# Prints PASS/FAIL per check; exit code = number of failures. A failure is recorded, not rerun silently (11).
set -uo pipefail
. "$(dirname "$0")/../setup/env.sh"
FAILS=0
ok()   { echo "PASS $1"; }
bad()  { echo "FAIL $1  -- $2"; FAILS=$((FAILS+1)); }
# req METHOD URL [BODY] -> "<status>\n<body>" from inside the sandbox (through the OpenShell proxy).
req() { sbx curl -s -m 15 -X "$1" -H 'Content-Type: application/json' ${3:+-d "$3"} -w '\n%{http_code}' "$2" 2>/dev/null; }
code() { tail -n1 <<<"$1"; }
expect() {  # expect ID DESC EXPECTED_CODE RESPONSE [BODY_SUBSTRING]
  local c; c="$(code "$4")"
  if [ "$c" = "$3" ] && { [ -z "${5:-}" ] || grep -q "$5" <<<"$4"; }; then ok "$1 $2 ($c)"; else bad "$1 $2" "got $c: $(head -c 200 <<<"$4" | tr '\n' ' ')"; fi
}
denied() {  # internet: blocked = curl 000 or proxy 403
  local c; c="$(code "$3")"
  case "$c" in 000|403) ok "$1 $2 ($c)";; *) bad "$1 $2" "got $c";; esac
}
W="http://$WORKER"

expect A1  "sandbox -> LLM /v1/models"          200 "$(req GET http://host.openshell.internal:8000/v1/models)" qwen3.8-27b
expect A2  "sandbox -> worker health"           200 "$(req GET "$W/api/health")" ok
expect A3  "sandbox -> POST agent-log allowed"  200 "$(req POST "$W/api/agent-log" '{"message":"acceptance: sandbox policy check"}')"
expect A4  "approve blocked by policy"          403 "$(req POST "$W/api/reports/1/approve" '{"approver":"sandbox"}')" policy_denied
expect A5  "confirm blocked by policy"          403 "$(req POST "$W/api/nodules/1/confirm" '{"long_mm":5,"short_mm":5,"by":"sandbox"}')" policy_denied
expect A6  "unlisted path blocked"              403 "$(req GET "$W/admin")" policy_denied
denied A7  "internet blocked"                       "$(req GET https://example.com)"
denied A8  "npm registry blocked"                   "$(req GET https://registry.npmjs.org)"

# A9-A10: MCP tools/list from the sandbox: 9 tools, none named *approv* or *confirm*.
INIT="$(sbx curl -s -m 15 -i -X POST -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"acceptance","version":"0"}}}' \
  "$W/mcp" 2>/dev/null)"
SID="$(grep -i '^mcp-session-id:' <<<"$INIT" | cut -d: -f2 | tr -d ' \r')"
[ -n "$SID" ] && ok "A9  MCP initialize (session $SID)" || bad "A9  MCP initialize" "no Mcp-Session-Id: $(head -c 200 <<<"$INIT" | tr '\n' ' ')"
sbx curl -s -m 15 -X POST -H 'Content-Type: application/json' -H "Mcp-Session-Id: $SID" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' "$W/mcp" >/dev/null 2>&1
TOOLS="$(sbx curl -s -m 15 -X POST -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -H "Mcp-Session-Id: $SID" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' "$W/mcp" 2>/dev/null)"
VERDICT="$(python3 -c '
import json, re, sys
names = sorted(t["name"] for t in json.loads(sys.argv[1])["result"]["tools"])
gate = [n for n in names if re.search("approv|confirm", n, re.I)]
print(("OK " if len(names) == 9 and not gate else "BAD ") + ",".join(names) + (" gate-tools=" + ",".join(gate) if gate else ""))' "$TOOLS" 2>&1)"
[[ "$VERDICT" == OK* ]] && ok "A10 tools/list: ${VERDICT#OK }" || bad "A10 tools/list (want 9, no approve/confirm)" "$VERDICT"
expect A11 "MCP DELETE allowed (teardown)"      204 "$(req DELETE "$W/mcp")"

if [ "${1:-}" = "--with-llm" ]; then
  # A12: the agent still sees and calls MCP tools under tools.profile=minimal (setup/30, unverified).
  # Calls OpenClaw's gateway chatCompletions on the host; the worker auto-logs agent tool calls (06).
  GT="$(nemoclaw "$SANDBOX" gateway-token --quiet)"
  curl -s -m 180 -H "Authorization: Bearer $GT" -H 'Content-Type: application/json' \
    -d '{"model":"openclaw","messages":[{"role":"user","content":"Acceptance check: call the list_studies tool once, then reply DONE. Do not call any other tool."}]}' \
    http://127.0.0.1:18789/v1/chat/completions >/dev/null
  curl -s "http://127.0.0.1:$WORKER_PORT/api/agent-log?limit=50" | grep -q 'list_studies' \
    && ok "A12 agent called an MCP tool (list_studies in agent-log)" \
    || bad "A12 agent MCP tool call" "no list_studies in /api/agent-log; see setup/30 fallback"
  # A13: hook trigger admits a run (06 step 6). Token read from the env file, never printed.
  HT="$(sed -n 's/^SPARKMD_HOOK_TOKEN=//p' "$SPARKMD_ENV_FILE")"
  R="$(curl -s -m 20 -w '\n%{http_code}' -H "Authorization: Bearer $HT" -H 'Content-Type: application/json' \
    -H "Idempotency-Key: acceptance-$(date +%s)" \
    -d '{"message":"Acceptance check: call list_studies once, then stop.","name":"spark-md","agentId":"main","deliver":false}' \
    http://127.0.0.1:18789/hooks/agent)"
  expect A13 "hook /hooks/agent admitted" 200 "$R" '"ok":true'
fi

echo "denials seen by OpenShell (07: visible in logs):"
openshell logs "$SANDBOX" 2>/dev/null | grep -iE 'denied|policy_denied' | tail -n 5 || true
echo "failures: $FAILS"
exit "$FAILS"
