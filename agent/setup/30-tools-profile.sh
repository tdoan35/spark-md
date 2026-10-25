#!/usr/bin/env bash
# 00 §Agent tools: disable OpenClaw's own file, shell, web and messaging tools; most restrictive profile.
# The agent keeps only the spark-md-worker MCP tools (none of them confirms or approves).
set -euo pipefail
. "$(dirname "$0")/env.sh"

sbx openclaw config set tools.profile minimal
sbx openclaw config set tools.deny '["group:fs","group:runtime","group:web","group:messaging","group:automation","group:ui","group:nodes","browser","canvas"]'
sbx openclaw config get tools
# UNVERIFIED: whether profile "minimal" also hides MCP server tools. tests/acceptance.sh check A6
# proves the agent still calls them. If A6 fails: `sbx openclaw config unset tools.profile` and keep
# the deny list (it still removes fs/shell/web/messaging), then re-run A6.
