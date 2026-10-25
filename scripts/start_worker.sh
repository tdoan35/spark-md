#!/usr/bin/env bash
# Worker only: LLM/OpenShell are brought up separately. Never installs or downloads.
# Box: SPARKMD_HOME=/srv/spark-md SPARKMD_MODELS=/drive/models scripts/start_worker.sh
# Mac: SPARKMD_HOME=/tmp/spark-md SPARKMD_PORT=8110 scripts/start_worker.sh
# Optional SPARKMD_PYTHON selects the box's offline venv; default is repo .venv.
# Loads SPARKMD_ENV_FILE (default $SPARKMD_HOME/.env) before applying defaults.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
case "$(uname -s)" in
  Darwin) DEFAULT_HOME="$HOME/.local/share/spark-md"; DEFAULT_BIND=127.0.0.1; DEFAULT_TOKEN_CMD='' ;;
  Linux) DEFAULT_HOME=/srv/spark-md; DEFAULT_BIND=0.0.0.0; DEFAULT_TOKEN_CMD='nemoclaw spark-md-openclaw gateway-token --quiet' ;;
  *) echo 'start_worker: supported hosts are macOS and Linux' >&2; exit 1 ;;
esac
export SPARKMD_HOME="${SPARKMD_HOME:-$DEFAULT_HOME}"
ENV_FILE="${SPARKMD_ENV_FILE:-$SPARKMD_HOME/.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  source "$ENV_FILE"
  set +a
fi
export SPARKMD_BIND="${SPARKMD_BIND:-$DEFAULT_BIND}"
export SPARKMD_PORT="${SPARKMD_PORT:-8100}"
export SPARKMD_MODELS="${SPARKMD_MODELS:-$SPARKMD_HOME/models}"
export SPARKMD_LLM_URL="${SPARKMD_LLM_URL:-http://127.0.0.1:8000/v1}"
export SPARKMD_SANDBOX_ADDR="${SPARKMD_SANDBOX_ADDR:-10.77.0.1}"
export SPARKMD_ASK_TOKEN_CMD="${SPARKMD_ASK_TOKEN_CMD-$DEFAULT_TOKEN_CMD}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 NEMOCLAW_DISABLE_TELEMETRY=1
PYTHON="${SPARKMD_PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  echo 'start_worker: set SPARKMD_PYTHON to an existing offline Python 3.12 venv interpreter' >&2
  exit 1
fi
cd -- "$ROOT"
"$PYTHON" -c 'import sys; assert sys.version_info >= (3, 12), "Python >=3.12 required"; import fastapi, httpx, nibabel, numpy, PIL, pydantic, pydicom, scipy, uvicorn; import sparkmd.imaging, sparkmd.rules'
if [[ "$SPARKMD_BIND" == 0.0.0.0 ]]; then
  echo 'Worker listening on all IPv4 interfaces; external interfaces must already be firewalled.' >&2
fi
printf 'Worker: bind=%s:%s home=%s models=%s\n' "$SPARKMD_BIND" "$SPARKMD_PORT" "$SPARKMD_HOME" "$SPARKMD_MODELS"
exec "$PYTHON" -m sparkmd
