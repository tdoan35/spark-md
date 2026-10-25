# Sourced by every agent/setup and agent/tests script. Box-side, run as ty after R8 (07 §Build steps).
export PATH="$HOME/.local/bin:$PATH"
export NEMOCLAW_DISABLE_TELEMETRY=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
SANDBOX="${SANDBOX:-spark-md-openclaw}"
# Worker as seen from the sandbox: 10.77.0.1 on spark0 (00); 172.17.0.1 (docker0) is the zero-sudo test fallback (07 Gotcha 7).
WORKER_HOST="${WORKER_HOST:-10.77.0.1}"
WORKER_PORT="${WORKER_PORT:-8100}"
WORKER="$WORKER_HOST:$WORKER_PORT"
SPARKMD_HOME="${SPARKMD_HOME:-/srv/spark-md}"
# Holds SPARKMD_HOOK_URL / SPARKMD_HOOK_TOKEN for the worker (00 §Env). Never committed.
SPARKMD_ENV_FILE="${SPARKMD_ENV_FILE:-$SPARKMD_HOME/.env}"
# timeout + closed stdin: one exec hung for 10+ min on the box (Oct 25) and stalled the suite.
sbx() { timeout "${SBX_TIMEOUT:-120}" openshell sandbox exec -n "$SANDBOX" -- "$@" </dev/null; }
