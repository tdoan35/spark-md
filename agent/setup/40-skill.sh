#!/usr/bin/env bash
# 07 §Confirm-flow update: install the two-phase triage skill as the workspace AGENTS.md.
# base64 as an argument, so it does not depend on `sandbox exec` forwarding stdin.
set -euo pipefail
. "$(dirname "$0")/env.sh"

SKILL="$(dirname "$0")/../skill/AGENTS.md"
B64="$(base64 < "$SKILL" | tr -d '\n')"
sbx sh -c "echo '$B64' | base64 -d > /sandbox/.openclaw/workspace/AGENTS.md"
[ "$(sbx sha256sum /sandbox/.openclaw/workspace/AGENTS.md | cut -d' ' -f1)" = "$(sha256sum "$SKILL" | cut -d' ' -f1)" ] \
  && echo "skill installed" || { echo "skill hash mismatch"; exit 1; }
