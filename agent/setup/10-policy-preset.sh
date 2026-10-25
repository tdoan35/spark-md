#!/usr/bin/env bash
# 07 §Worker policy preset (+ Gotchas 3, 4, 6; C5 gotcha for GET/DELETE /mcp). Enforce mode only.
# Allows only the agent routes from 00 §Worker API. confirm and approve are not listed, so enforce denies them.
set -euo pipefail
. "$(dirname "$0")/env.sh"

apply() {
  openshell policy update "$SANDBOX" \
    --add-endpoint "$WORKER::rest:enforce" \
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

# Gotcha 4: an access preset (read-write) expands to broad METHOD ** rules that openshell 0.0.116
# merges with the explicit ones (box, Oct 25), so the endpoint has an empty access segment. Check
# that this endpoint is enforce and holds exactly the explicit rules.
check() {
  openshell policy get "$SANDBOX" --full -o json | python3 -c '
import json, sys
host, port, doc = sys.argv[1], int(sys.argv[2]), json.load(sys.stdin)
eps = []
def walk(o):
    if isinstance(o, dict):
        if o.get("host") == host and o.get("port") == port: eps.append(o)
        for v in o.values(): walk(v)
    elif isinstance(o, list):
        for v in o: walk(v)
walk(doc)
bad = [] if eps else ["no endpoint for %s:%d" % (host, port)]
for ep in eps:
    if ep.get("enforcement") != "enforce": bad.append("not enforce: %s" % ep.get("enforcement"))
    for r in ep.get("rules", []):
        a = r.get("allow", {})
        if a.get("path") in ("**", "/**"): bad.append("broad rule: %s %s" % (a.get("method"), a.get("path")))
print("\n".join(bad) or "policy OK: enforce, explicit rules only (%d)" % sum(len(e.get("rules", [])) for e in eps))
sys.exit(1 if bad else 0)' "$WORKER_HOST" "$WORKER_PORT"
}

apply
check

# Gotcha 6: drop OpenShell's cloud presets. Keep _provider_* and managed_inference (the LLM route).
for rule in clawhub npm_registry nvidia openclaw_api openclaw_docs; do
  openshell policy update "$SANDBOX" --remove-rule "$rule" --wait || echo "($rule already absent)"
done
openshell policy get "$SANDBOX" --full -o json > "${TMPDIR:-/tmp}/spark-md-policy.json"
echo "final policy: ${TMPDIR:-/tmp}/spark-md-policy.json (review: no clawhub/npm/nvidia/openclaw_api/openclaw_docs)"
