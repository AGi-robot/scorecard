#!/bin/bash
# Round 1b (judge: Saluki then DeepSeek over all baseline renders) followed
# by round 2 (multi-pass production loop on the top 6; MiniCPM benched).
# Sequential, one standalone server at a time, resumable by output files.
set -uo pipefail

BASE=/home/oppa-ai/AGi/diagnostic/scorecard/benchmarks
EVAL=$BASE/grace_canvas_eval/grace_canvas_eval.py
JUDGE=$BASE/grace_canvas_eval/judge_round.py
OUT=$BASE/grace_canvas_eval/results
RENDERS=$BASE/grace_canvas_eval/renders
OUT2=$BASE/grace_canvas_eval/results/round2
RENDERS2=$BASE/grace_canvas_eval/renders/round2
LOGDIR=$BASE/.logs
ENV=/home/oppa-ai/.venvs/grace-canvas-eval/bin/python
INHIBIT=$BASE/run_with_inhibit.sh
SERVER=/home/oppa-ai/llama.cpp/build/bin/llama-server
PORT=8090
URL=http://127.0.0.1:$PORT/v1
MMPROJ_SWIFT=/home/oppa-ai/AGi/models/swift15-qwen3.8-27b/mmproj-Swift-1.5-Qwen3.8-27B-Uncensored-MTP-BF16.gguf
MMPROJ_DEEPSEEK=/home/oppa-ai/AGi/models/deepseek-v4-pro-qwen3.5-9b/DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic.mmproj-f16.gguf
SERVER_PID=

mkdir -p "$OUT" "$RENDERS" "$OUT2" "$RENDERS2" "$LOGDIR"
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

run_judge() {
  local model=$1 label=$2
  if [ -f "$OUT/judge-$label.json" ]; then
    log "SKIP judge-$label (exists)"
    return 0
  fi
  log "===== Judge: $label ($model) over baseline renders ====="
  AGI_REPO=/home/oppa-ai/AGi bash "$INHIBIT" "$ENV" "$JUDGE" \
    --judge-base-url "$URL" --judge-model "$model" --judge-label "$label" \
    --renders "$RENDERS" --results "$OUT" --out "$OUT/judge-$label.json" \
    2>&1 | tee -a "$LOGDIR/judge-$label.log"
}

run_round2() {
  local model=$1 label=$2; shift 2
  if [ -f "$OUT2/$label.json" ]; then
    log "SKIP round2 $label (exists)"
    return 0
  fi
  log "===== Round 2 (multi-pass): $label ($model) ====="
  AGI_REPO=/home/oppa-ai/AGi bash "$INHIBIT" "$ENV" "$EVAL" \
    --base-url "$URL" --model "$model" --label "$label" \
    --reasoning-effort medium --max-tokens 6144 --vision-passes \
    --out "$OUT2/$label.json" --out-dir "$RENDERS2/$label" \
    2>&1 | tee -a "$LOGDIR/round2-$label.log"
  log "Round 2 done: $label"
}

trap 'stop_server' EXIT

# ---- Round 1b: judges (vision servers) ----
if [ ! -f "$OUT/judge-saluki-27b.json" ]; then
  log "Loading saluki-27b as judge"
  start_server "$LOGDIR/judge-saluki-server.log" \
    --alias saluki-27b \
    --model /home/oppa-ai/AGi/models/saluki-27b/Underdog-Saluki-27B-1.0-IQ2-mix-MTP-abliterated.gguf \
    --mmproj "$MMPROJ_SWIFT" --jinja --reasoning-effort medium --reasoning-budget 2048 \
    --ctx-size 32768 --cache-type-k q8_0 --cache-type-v q8_0 && \
    run_judge saluki-27b saluki-27b
  stop_server
fi

if [ ! -f "$OUT/judge-deepseek-9b.json" ]; then
  log "Loading deepseek as judge"
  CUDA_VISIBLE_DEVICES=0 start_server "$LOGDIR/judge-deepseek-server.log" \
    --alias deepseek-v4-pro-qwen3.5-9b \
    --model /home/oppa-ai/AGi/models/deepseek-v4-pro-qwen3.5-9b/DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic.i1-Q4_K_M.gguf \
    --mmproj "$MMPROJ_DEEPSEEK" --jinja --reasoning-effort medium --reasoning-budget 2048 \
    --ctx-size 32768 --cache-type-k q8_0 --cache-type-v q8_0 && \
    run_judge deepseek-v4-pro-qwen3.5-9b deepseek-9b
  stop_server
fi

# ---- Round 2: multi-pass, top 6 (MiniCPM benched at 0.4048) ----
if [ ! -f "$OUT2/swift15-qwen3.8-27b-local.json" ]; then
  log "Loading swift15-qwen3.8-27b for round 2"
  start_server "$LOGDIR/round2-swift-server.log" \
    --alias swift15-qwen3.8-27b \
    --model /home/oppa-ai/AGi/models/swift15-qwen3.8-27b/Swift-1.5-Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf \
    --mmproj "$MMPROJ_SWIFT" --jinja --reasoning-effort medium --reasoning-budget 2048 \
    --ctx-size 32768 --cache-type-k q5_0 --cache-type-v q5_0 && \
    run_round2 swift15-qwen3.8-27b swift15-qwen3.8-27b-local
  stop_server
fi

if [ ! -f "$OUT2/saluki-27b.json" ]; then
  log "Loading saluki-27b for round 2"
  start_server "$LOGDIR/round2-saluki-server.log" \
    --alias saluki-27b \
    --model /home/oppa-ai/AGi/models/saluki-27b/Underdog-Saluki-27B-1.0-IQ2-mix-MTP-abliterated.gguf \
    --mmproj "$MMPROJ_SWIFT" --jinja --reasoning-effort medium --reasoning-budget 2048 \
    --ctx-size 32768 --cache-type-k q8_0 --cache-type-v q8_0 && \
    run_round2 saluki-27b saluki-27b
  stop_server
fi

if [ ! -f "$OUT2/ministral3-8b.json" ]; then
  log "Loading ministral-3-8b for round 2 (own mmproj wired for vision)"
  CUDA_VISIBLE_DEVICES=0 start_server "$LOGDIR/round2-ministral-server.log" \
    --alias ministral-3-8b-uncensored \
    --model /home/oppa-ai/AGi/models/ministral3-8b/Ministral-3-8B-Uncensored.i1-Q4_K_M.gguf \
    --mmproj /home/oppa-ai/AGi/models/ministral3-8b/mmproj-BF16.gguf \
    --ctx-size 24576 --cache-type-k q4_0 --cache-type-v q4_0 && \
    run_round2 ministral-3-8b-uncensored ministral3-8b
  stop_server
fi

if [ ! -f "$OUT2/deepseek-v4-pro-qwen3.5-9b.json" ]; then
  log "Loading deepseek for round 2"
  CUDA_VISIBLE_DEVICES=0 start_server "$LOGDIR/round2-deepseek-server.log" \
    --alias deepseek-v4-pro-qwen3.5-9b \
    --model /home/oppa-ai/AGi/models/deepseek-v4-pro-qwen3.5-9b/DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic.i1-Q4_K_M.gguf \
    --mmproj "$MMPROJ_DEEPSEEK" --jinja --reasoning-effort medium --reasoning-budget 2048 \
    --ctx-size 32768 --cache-type-k q8_0 --cache-type-v q8_0 && \
    run_round2 deepseek-v4-pro-qwen3.5-9b deepseek-v4-pro-qwen3.5-9b
  stop_server
fi

if [ ! -f "$OUT2/neohorse-1-4b.json" ]; then
  log "Loading neohorse-1-4b for round 2"
  CUDA_VISIBLE_DEVICES=0 start_server "$LOGDIR/round2-neohorse-server.log" \
    --alias neohorse-1-4b \
    --model /opt/agi/models/neohorse-1-4b/NeoHorse-1-4B-Q4_K_M.gguf \
    --jinja --reasoning-effort medium --reasoning-budget 2048 \
    --ctx-size 16384 && \
    run_round2 neohorse-1-4b neohorse-1-4b
  stop_server
fi

if [ ! -f "$OUT2/agents-a1-4b.json" ]; then
  log "Loading agents-a1-4b for round 2"
  CUDA_VISIBLE_DEVICES=0 start_server "$LOGDIR/round2-agents-server.log" \
    --alias agents-a1-4b \
    --model /opt/agi/models/agents-a1-4b/Agents-A1-4B-Q4_K_M.gguf \
    --mmproj /opt/agi/models/agents-a1-4b/Agents-A1-4B-mmproj.gguf \
    --jinja --reasoning-effort medium --reasoning-budget 2048 \
    --ctx-size 16384 && \
    run_round2 agents-a1-4b agents-a1-4b
  stop_server
fi

log "Round 1b + round 2 complete."
ls -1 "$OUT"/judge-*.json "$OUT2"/*.json 2>/dev/null
