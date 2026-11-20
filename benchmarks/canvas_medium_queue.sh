#!/bin/bash
# Canvas eval, production recipe: thinking ON with reasoning effort medium,
# max_tokens 6144 (README: effort off 7/10, low 8/10, medium 9/10).
#
# Sequential, one standalone llama-server per model, resumable by result JSON.
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
MMPROJ_SWIFT=/home/oppa-ai/AGi/models/swift15-qwen3.8-27b/mmproj-Swift-1.5-Qwen3.8-27B-Uncensored-MTP-BF16.gguf
SERVER_PID=
# Thinking controls applied at the server (llama.cpp ignores the request field).
THINK=(--jinja --reasoning-effort medium --reasoning-budget 2048)

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
  log "===== Canvas eval (effort medium): $label ($model) ====="
  AGI_REPO=/home/oppa-ai/AGi bash "$INHIBIT" "$ENV" "$EVAL" \
    --base-url "$URL" --model "$model" --label "$label" \
    --reasoning-effort medium --max-tokens 6144 --single-pass \
    --out "$OUT/$label.json" --out-dir "$RENDERS/$label" \
    2>&1 | tee -a "$LOGDIR/canvas-medium-$label.log"
  log "Canvas eval done: $label"
}

trap 'stop_server' EXIT

# 1. Ministral 3 8B -- no thinking mode; effort flags are inert but harmless.
if [ ! -f "$OUT/ministral3-8b.json" ]; then
  log "Loading ministral-3-8b-uncensored"
  CUDA_VISIBLE_DEVICES=0 start_server "$LOGDIR/medium-ministral-server.log" \
    --alias ministral-3-8b-uncensored \
    --model /home/oppa-ai/AGi/models/ministral3-8b/Ministral-3-8B-Uncensored.i1-Q4_K_M.gguf \
    --ctx-size 24576 --cache-type-k q4_0 --cache-type-v q4_0 && \
    run_canvas ministral-3-8b-uncensored ministral3-8b
  stop_server
fi

# 2. Swift 27B
if [ ! -f "$OUT/swift15-qwen3.8-27b-local.json" ]; then
  log "Loading swift15-qwen3.8-27b"
  start_server "$LOGDIR/medium-swift-server.log" \
    --alias swift15-qwen3.8-27b \
    --model /home/oppa-ai/AGi/models/swift15-qwen3.8-27b/Swift-1.5-Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf \
    --mmproj "$MMPROJ_SWIFT" "${THINK[@]}" \
    --ctx-size 32768 --cache-type-k q5_0 --cache-type-v q5_0 && \
    run_canvas swift15-qwen3.8-27b swift15-qwen3.8-27b-local
  stop_server
fi

# 3. Saluki 27B
if [ ! -f "$OUT/saluki-27b.json" ]; then
  log "Loading saluki-27b"
  start_server "$LOGDIR/medium-saluki-server.log" \
    --alias saluki-27b \
    --model /home/oppa-ai/AGi/models/saluki-27b/Underdog-Saluki-27B-1.0-IQ2-mix-MTP-abliterated.gguf \
    --mmproj "$MMPROJ_SWIFT" "${THINK[@]}" \
    --ctx-size 32768 --cache-type-k q8_0 --cache-type-v q8_0 && \
    run_canvas saluki-27b saluki-27b
  stop_server
fi

# 4. DeepSeek-V4-Pro-Qwen3.5 9B
if [ ! -f "$OUT/deepseek-v4-pro-qwen3.5-9b.json" ]; then
  log "Loading deepseek-v4-pro-qwen3.5-9b"
  CUDA_VISIBLE_DEVICES=0 start_server "$LOGDIR/medium-deepseek-server.log" \
    --alias deepseek-v4-pro-qwen3.5-9b \
    --model /home/oppa-ai/AGi/models/deepseek-v4-pro-qwen3.5-9b/DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic.i1-Q4_K_M.gguf \
    --mmproj /home/oppa-ai/AGi/models/deepseek-v4-pro-qwen3.5-9b/DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic.mmproj-f16.gguf \
    "${THINK[@]}" --ctx-size 32768 --cache-type-k q8_0 --cache-type-v q8_0 && \
    run_canvas deepseek-v4-pro-qwen3.5-9b deepseek-v4-pro-qwen3.5-9b
  stop_server
fi

log "Canvas effort-medium runs complete."
