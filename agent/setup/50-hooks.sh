#!/usr/bin/env bash
# 06 Build step 6 / 07 trigger: openclaw.json hooks block + the gateway chatCompletions endpoint (/api/ask, 07 §C5),
# then gateway restart (also applies 20/30). Run last. The hook token is generated here, written only to $SPARKMD_ENV_FILE (mode 600) and
# the sandbox config; it is never echoed, never committed, and distinct from gateway.auth.token.
set -euo pipefail
. "$(dirname "$0")/env.sh"

umask 077
mkdir -p "$(dirname "$SPARKMD_ENV_FILE")"
touch "$SPARKMD_ENV_FILE"
if grep -q '^SPARKMD_HOOK_TOKEN=' "$SPARKMD_ENV_FILE"; then
  TOKEN="$(sed -n 's/^SPARKMD_HOOK_TOKEN=//p' "$SPARKMD_ENV_FILE")"
else
  TOKEN="smd_$(python3 -c 'import secrets; print(secrets.token_hex(32))')"  # prefix: never numeric, never a flag
  echo "SPARKMD_HOOK_TOKEN=$TOKEN" >> "$SPARKMD_ENV_FILE"
fi
grep -q '^SPARKMD_HOOK_URL=' "$SPARKMD_ENV_FILE" \
  || echo "SPARKMD_HOOK_URL=http://127.0.0.1:18789/hooks/agent" >> "$SPARKMD_ENV_FILE"
chmod 600 "$SPARKMD_ENV_FILE"

# 06 step 6: hooks: {enabled: true, token, path: "/hooks", allowedAgentIds: ["main"], allowRequestSessionKey: false}
sbx openclaw config set hooks.enabled true
sbx openclaw config set hooks.token "$TOKEN" >/dev/null
sbx openclaw config set hooks.path /hooks
sbx openclaw config set hooks.allowedAgentIds '["main"]'
sbx openclaw config set hooks.allowRequestSessionKey false
sbx openclaw config set gateway.http.endpoints.chatCompletions.enabled true
nemoclaw "$SANDBOX" gateway restart
echo "hooks enabled; worker reads SPARKMD_HOOK_URL/SPARKMD_HOOK_TOKEN from $SPARKMD_ENV_FILE (restart the worker)"
