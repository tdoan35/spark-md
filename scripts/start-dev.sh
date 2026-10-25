#!/usr/bin/env bash
# Spark MD dev loop on the Mac: mock worker (8101) behind Vite (5173) with an /api proxy.
# Production on the box: worker serves ui/dist at 127.0.0.1:8100 and Electron loads it.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d ui/node_modules ] || { echo "run npm ci in ui/ first"; exit 1; }
MOCK_PORT=8101 MOCK_SPEED=${MOCK_SPEED:-1} node ui/mock/server.mjs &
MOCK=$!
trap 'kill $MOCK 2>/dev/null' EXIT
cd ui
SPARKMD_UI_TARGET=http://127.0.0.1:8101 npx vite --port 5173 --strictPort &
VITE=$!
echo "UI: http://127.0.0.1:5173/  ·  Electron: SPARKMD_UI_URL=http://127.0.0.1:5173/ npx electron ."
wait $VITE
