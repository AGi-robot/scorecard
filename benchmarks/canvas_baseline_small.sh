#!/bin/bash
# Canvas baseline (single-pass, production schema/transport) for the 3 small
# models. Runs after the main 4-model queue: wait for its results, then go.
set -uo pipefail

BASE=/home/oppa-ai/AGi/diagnostic/scorecard/benchmarks
EVAL=$BASE/grace_canvas_eval/grace_canvas_eval.py
OUT=$BASE/grace_canvas_eval/results
RENDERS=$BASE/grace_canvas_eval/renders
LOGDIR=$BASE/.logs
ENV=/home/oppa-ai/.venvs/grace-canvas-eval/bin/python
INHIBIT=$BASE/run_with_inhibit.sh
SERVER=/home/oppa-ai/llama.cpp/build/bin/llama-server
PORT=8090
URL=http://127.0.0.1:$PORT/v1
SERVER_PID=

mkdir -p "$OUT" "$RENDERS" "$LOGDIR"
log() { echo "[$(date)] $*"; }

start_server() {
  local log=$1; shift
  setsid nohup "$SERVER" --host 127.0.0.1 --port "$PORT" \
    --log-colors off --n-gpu-layers 999 --flash-attn on "$@" \
    > "$log" 2>&1 < /dev/null &
  SERVER_PID=$!
  for i in $(seq 1 90); do
    curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && return 0
    kill -0 "$SERVER_PID" 2>/dev/null || { log "server died, see $log"; tail -25 "$log"; return 1; }
    sleep 2
  done
  log "server health timeout, see $log"
  return 1
}

stop_server() {
  [ -n "${SERVER_PID:-}" ] || return 0
  kill -TERM "$SERVER_PID" 2>/dev/null
  for i in $(seq 1 30); do kill -0 "$SERVER_PID" 2>/dev/null || break; sleep 1; done
  kill -KILL "$SERVER_PID" 2>/dev/null
  pkill -f "llama-server.*--port $PORT" 2>/dev/null
  sleep 3
  SERVER_PID=
}

run_canvas() {
  local model=$1 label=$2
  if [ -f "$OUT/$label.json" ]; then
    log "SKIP $label (result exists)"
    return 0
  fi
  log "===== Canvas baseline (single-pass): $label ($model) ====="
  AGI_REPO=/home/oppa-ai/AGi bash "$INHIBIT" "$ENV" "$EVAL" \
    --base-url "$URL" --model "$model" --label "$label" \
    --reasoning-effort medium --max-tokens 6144 --single-pass \
    --out "$OUT/$label.json" --out-dir "$RENDERS/$label" \
    2>&1 | tee -a "$LOGDIR/canvas-baseline-$label.log"
  log "Canvas baseline done: $label"
}

trap 'stop_server' EXIT

# Wait for the main queue's four results before touching the GPUs.
log "Waiting for main-queue results (ministral, swift, saluki, deepseek)..."
for m in ministral3-8b swift15-qwen3.8-27b-local saluki-27b deepseek-v4-pro-qwen3.5-9b; do
  while [ ! -f "$OUT/$m.json" ]; do sleep 20; done
done
log "Main queue complete. Starting small-model baselines."

# 1. MiniCPM5 2B
if [ ! -f "$OUT/minicpm5-2b.json" ]; then
  log "Loading minicpm5-2b"
  CUDA_VISIBLE_DEVICES=0 start_server "$LOGDIR/baseline-minicpm-server.log" \
    --alias minicpm5-2b \
    --model /opt/agi/models/minicpm5-2b/MiniCPM5-2B-Q8_0.gguf \
    --jinja --reasoning-effort medium --reasoning-budget 2048 \
    --ctx-size 16384 && \
    run_canvas minicpm5-2b minicpm5-2b
  stop_server
fi

# 2. NeoHorse 1 4B
if [ ! -f "$OUT/neohorse-1-4b.json" ]; then
  log "Loading neohorse-1-4b"
  CUDA_VISIBLE_DEVICES=0 start_server "$LOGDIR/baseline-neohorse-server.log" \
    --alias neohorse-1-4b \
    --model /opt/agi/models/neohorse-1-4b/NeoHorse-1-4B-Q4_K_M.gguf \
    --jinja --reasoning-effort medium --reasoning-budget 2048 \
    --ctx-size 16384 && \
    run_canvas neohorse-1-4b neohorse-1-4b
  stop_server
fi

# 3. Agents A1 4B
if [ ! -f "$OUT/agents-a1-4b.json" ]; then
  log "Loading agents-a1-4b"
  CUDA_VISIBLE_DEVICES=0 start_server "$LOGDIR/baseline-agents-server.log" \
    --alias agents-a1-4b \
    --model /opt/agi/models/agents-a1-4b/Agents-A1-4B-Q4_K_M.gguf \
    --jinja --reasoning-effort medium --reasoning-budget 2048 \
    --ctx-size 16384 && \
    run_canvas agents-a1-4b agents-a1-4b
  stop_server
fi

log "Small-model baselines complete."
ls -1 "$OUT"/*.json | rg 'ministral3-8b|swift15-qwen3.8-27b-local|saluki-27b|deepseek-v4-pro|minicpm5-2b|neohorse-1-4b|agents-a1-4b'
