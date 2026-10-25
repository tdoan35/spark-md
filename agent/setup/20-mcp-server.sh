#!/usr/bin/env bash
# 07 §C5 wiring: OpenClaw MCP server spark-md-worker -> http://$WORKER/mcp, requestTimeoutMs 60000
# (06: the worker's MCP long-poll SPARKMD_MCP_WAIT_S must stay <= 50 s, under this timeout).
set -euo pipefail
. "$(dirname "$0")/env.sh"

sbx openclaw mcp add spark-md-worker --transport streamable-http --url "http://$WORKER/mcp" \
  || echo "(spark-md-worker exists; updating url)"
# `mcp add` probes the server and writes nothing if the worker is down (box, Oct 25), so set every key.
sbx openclaw config set mcp.servers.spark-md-worker.transport streamable-http
sbx openclaw config set mcp.servers.spark-md-worker.url "http://$WORKER/mcp"
sbx openclaw config set mcp.servers.spark-md-worker.requestTimeoutMs 60000
sbx openclaw config get mcp.servers.spark-md-worker
