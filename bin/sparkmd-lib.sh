# shellcheck shell=bash
# Shared by bin/sparkmd-{start,stop,status,sudo}. Spec: docs/build/01-box-setup.md §Start-all, 12 §Box bring-up.
# Sourced, not run. No network, no downloads, no sudo (sudo commands are only ever printed), no :latest tags.

BIN_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$BIN_DIR")"
export PATH="$HOME/.local/bin:$PATH"

# --- config (event box defaults from W's handoff, Oct 25; every value overridable from the environment) ---
export SPARKMD_HOME="${SPARKMD_HOME:-/home/dell/spark-md-runtime-w}"
export SPARKMD_ENV_FILE="${SPARKMD_ENV_FILE:-/home/dell/spark-md/.env}"      # hook token/URL; REQUIRED for the worker
export SPARKMD_PYTHON="${SPARKMD_PYTHON:-/home/dell/.venvs/spark-md/bin/python}"
export SPARKMD_MODELS="${SPARKMD_MODELS:-/home/dell/spark-md/models}"
export SPARKMD_BIND="${SPARKMD_BIND:-0.0.0.0}"
export SPARKMD_PORT="${SPARKMD_PORT:-8100}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 NEMOCLAW_DISABLE_TELEMETRY=1
LOG_DIR="${SPARKMD_LOG_DIR:-$HOME/logs}"
LLM_DIR="${SPARKMD_LLM_DIR:-$HOME/qwen38-27b-tensorfold}"
LLM_URL="${SPARKMD_LLM_BASE:-http://127.0.0.1:8000/v1}"
LLM_NAME=qwen3.8-27b
SANDBOX="${SANDBOX:-spark-md-openclaw}"
GATEWAY_UNIT=nemoclaw-openshell-gateway.service
DOCKER_PROXY_SOCK="/run/user/$(id -u)/docker-proxy.sock"
WORKER_SESSION="${SPARKMD_WORKER_SESSION:-sparkmd-worker}"
WORKER_URL="http://127.0.0.1:$SPARKMD_PORT"
SPARK0_ADDR=10.77.0.1
FW_MARKER=/run/sparkmd-fw.ok                      # written by bin/sparkmd-sudo; /run is tmpfs, so it dies with the rules at reboot
FW_PORTS=8000,8100
ASR_BIN="${SPARKMD_WHISPER_BIN:-$HOME/sparkmd-voice/whisper.cpp/build/bin/whisper-server}"
ASR_MODEL_DIR="${SPARKMD_WHISPER_MODELS:-$SPARKMD_MODELS/asr/whispercpp}"
ASR_SESSION=sparkmd-asr
TTS_CONTAINER=sparkmd-tts
TTS_CONFIG="${SPARKMD_TTS_CONFIG:-$HOME/sparkmd-voice/tts-config}"
TTS_MODEL="${SPARKMD_TTS_MODEL:-$SPARKMD_MODELS/tts/Qwen3-TTS-12Hz-1.7B-Base}"
ELECTRON="$REPO/ui/node_modules/electron/dist/electron"
MEM_FLOOR_GIB=15
mkdir -p "$LOG_DIR"

# --- output: one line per step, OK / WARN / FAIL -----------------------------------------------------
N_OK=0; N_WARN=0; N_FAIL=0
say() {  # say LEVEL STEP MESSAGE
  case "$1" in OK) N_OK=$((N_OK+1));; WARN) N_WARN=$((N_WARN+1));; FAIL) N_FAIL=$((N_FAIL+1));; esac
  printf "%-4s %-8s %s%s\n" "$1" "$2" "$3" "${SPARKMD_DRYRUN:+  [dry run]}"
}
hint() { printf '       %s\n' "$@"; }
summary() { printf -- '-- %d OK, %d WARN, %d FAIL\n' "$N_OK" "$N_WARN" "$N_FAIL"; }

# act CMD...: run a mutating command, or only print it when SPARKMD_DRYRUN is set
act() { if [[ -n ${SPARKMD_DRYRUN:-} ]]; then hint "DRY: $*"; return 0; fi; "$@"; }

# only STEP: honour --only a,b (default: all)
ONLY=""
want() { [[ -z "$ONLY" || ",$ONLY," == *",$1,"* ]]; }

# wait_for SECONDS CMD...: poll every 2 s until CMD succeeds
wait_for() { [[ -n ${SPARKMD_DRYRUN:-} ]] && return 0; local t=$1 end; shift; end=$((SECONDS+t)); until "$@"; do (( SECONDS < end )) || return 1; sleep 2; done; }
alive() { kill -0 "$1" 2>/dev/null; }
strip_ansi() { sed 's/\x1b\[[0-9;]*m//g'; }

# --- probes (read-only; return 0 = up) ------------------------------------------------------------
c_spark0()  { ip -4 addr show spark0 2>/dev/null | grep -q "inet $SPARK0_ADDR/"; }
c_llm()     { curl -sf -m 4 "$LLM_URL/models" 2>/dev/null | grep -q "\"$LLM_NAME\""; }
c_llm_container() { [[ "$(docker inspect -f '{{.State.Running}}' qwen38-27b-tf 2>/dev/null)" == true ]]; }
c_fw()      { [[ -e $FW_MARKER ]]; }
c_proxy()   { [[ -S $DOCKER_PROXY_SOCK ]]; }
c_gateway() { systemctl --user is-active --quiet "$GATEWAY_UNIT" 2>/dev/null; }
c_sbx_ready() { openshell sandbox list 2>/dev/null | strip_ansi | grep -E "^\s*$SANDBOX\b" | grep -q Ready; }
c_sbx_llm() { local i; for i in 1 2; do timeout 30 openshell sandbox exec -n "$SANDBOX" -- curl -s -m 8 http://host.openshell.internal:8000/v1/models 2>/dev/null | grep -q "\"$LLM_NAME\"" && return 0; sleep 2; done; return 1; }
c_worker()  { curl -sf -m 4 "$WORKER_URL/api/health" 2>/dev/null | grep -q '"status":"ok"'; }
c_worker_spark0() { curl -sf -m 4 "http://$SPARK0_ADDR:$SPARKMD_PORT/api/health" 2>/dev/null | grep -q '"status":"ok"'; }
c_asr()     { curl -s -m 3 -o /dev/null "http://127.0.0.1:8178/" 2>/dev/null; }
c_tts()     { curl -sf -m 3 http://127.0.0.1:8020/health 2>/dev/null | grep -q '"ok"'; }
c_ui_served() { [[ "$(curl -s -m 4 -o /dev/null -w '%{http_code}' "$WORKER_URL/")" == 200 ]]; }
ui_pid()    { pgrep -af "$ELECTRON" | grep -v -- '--type=' | awk '{print $1}' | head -n1; }
worker_session_pid() { tmux display-message -p -t "$WORKER_SESSION" '#{pane_pid}' 2>/dev/null; }
listener_pid() { ss -ltnpH "sport = :$1" 2>/dev/null | grep -o 'pid=[0-9]*' | head -n1 | cut -d= -f2; }
chrome_sandbox_ok() { local f="$REPO/ui/node_modules/electron/dist/chrome-sandbox"; [[ -u $f && "$(stat -c %U "$f")" == root ]]; }
mem_avail_gib() { awk '/MemAvailable/ {printf "%d", $2/1048576}' /proc/meminfo; }

# --- sudo commands: only ever printed (never run here); bin/sparkmd-sudo runs them as root --------------
phys_ifaces() { local d; for d in /sys/class/net/*; do [[ -e $d/device ]] && basename "$d"; done; }
# sudo_cmds [all]: the commands still needed (all = regardless of current state, for bin/sparkmd-sudo as root)
sudo_cmds() {
  local all="${1:-}" i
  if [[ -n $all ]] || ! c_spark0; then
    echo "ip link show spark0 >/dev/null 2>&1 || ip link add spark0 type dummy"
    echo "ip addr show spark0 | grep -q 'inet $SPARK0_ADDR/' || ip addr add $SPARK0_ADDR/32 dev spark0"
    echo "ip link set spark0 up"
  fi
  if [[ -n $all ]] || ! c_fw; then
    for i in $(phys_ifaces); do
      for t in iptables ip6tables; do
        echo "$t -C INPUT -i $i -p tcp -m multiport --dports $FW_PORTS -m comment --comment sparkmd-fw -j DROP 2>/dev/null || $t -I INPUT -i $i -p tcp -m multiport --dports $FW_PORTS -m comment --comment sparkmd-fw -j DROP"
      done
    done
    echo "touch $FW_MARKER"
  fi
  if [[ -n $all ]] || ! chrome_sandbox_ok; then      # ui/README.md: Electron on Linux aarch64 needs the SUID sandbox once
    echo "chown root:root $REPO/ui/node_modules/electron/dist/chrome-sandbox && chmod 4755 $REPO/ui/node_modules/electron/dist/chrome-sandbox"
  fi
}
print_sudo_hint() {
  local lines; lines="$(sudo_cmds)"
  [[ -n $lines ]] || return 0
  hint "needs sudo at the console (never run by this script). One line:  sudo bash $BIN_DIR/sparkmd-sudo"
  hint "or the exact commands (each as root):"
  while IFS= read -r l; do hint "  sudo bash -c '${l//\'/\'\\\'\'}'"; done <<<"$lines"
}
