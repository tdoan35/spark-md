#!/usr/bin/env bash
# 07 §Worker policy preset (+ Gotchas 3, 4, 6; C5 gotcha for GET/DELETE /mcp). Enforce mode only.
# Allows only the agent routes from 00 §Worker API. confirm and approve are not listed, so enforce denies them.
set -euo pipefail
. "$(dirname "$0")/env.sh"

apply() {
  openshell policy update "$SANDBOX" \
    --add-endpoint "$WORKER:read-write:rest:enforce" \
    --binary /usr/bin/curl --binary /usr/local/bin/node --binary /usr/local/bin/openclaw \
    --add-allow "$WORKER:GET:/api/**" \
    --add-allow "$WORKER:POST:/api/studies/*/select-series" \
    --add-allow "$WORKER:POST:/api/studies/*/analyze" \
    --add-allow "$WORKER:POST:/api/studies/*/reports" \
    --add-allow "$WORKER:POST:/api/studies/*/priority" \
    --add-allow "$WORKER:POST:/api/viewer/command" \
    --add-allow "$WORKER:POST:/api/agent-log" \
    --add-allow "$WORKER:POST:/mcp" \
    --add-allow "$WORKER:GET:/mcp" \
    --add-allow "$WORKER:DELETE:/mcp" \
    --wait
}

# Gotcha 4: the read-write access preset expands to broad METHOD /** rules; a second explicit
# update replaces them. Check the final rules and re-apply once if any broad write rule is left.
check() {
  openshell policy get "$SANDBOX" --full -o json | python3 -c '
import json, sys
host, doc = sys.argv[1], json.load(sys.stdin)
bad = []
def walk(o):
    if isinstance(o, dict):
        s = json.dumps(o)
        vals = {str(v) for v in o.values() if not isinstance(v, (dict, list))}
        if host in s and len(s) < 2000:
            if "audit" in vals: bad.append("audit mode: " + s[:200])
            if vals & {"/**", "**"} and vals & {"POST", "PUT", "PATCH", "DELETE", "*"}: bad.append("broad rule: " + s[:200])
        for v in o.values(): walk(v)
    elif isinstance(o, list):
        for v in o: walk(v)
walk(doc)
print("\n".join(bad) or "policy OK: enforce, explicit rules only")
sys.exit(1 if bad else 0)' "$WORKER_HOST"
}

apply
check || { echo "re-applying once (Gotcha 4)"; apply; check; }

# Gotcha 6: drop OpenShell's cloud presets. Keep _provider_* and managed_inference (the LLM route).
for rule in clawhub npm_registry nvidia openclaw_api openclaw_docs; do
  openshell policy update "$SANDBOX" --remove-rule "$rule" --wait || echo "($rule already absent)"
done
openshell policy get "$SANDBOX" --full -o json > "${TMPDIR:-/tmp}/spark-md-policy.json"
echo "final policy: ${TMPDIR:-/tmp}/spark-md-policy.json (review: no clawhub/npm/nvidia/openclaw_api/openclaw_docs)"
