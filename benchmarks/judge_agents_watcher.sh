#!/bin/bash
# Round 1b (part 2): Agent A1 judges all 56 baseline renders.
# Waits for round 2 to finish (agents-a1-4b.json in round2/), then serves
# agents-a1-4b with its own mmproj and runs the blind judge.
set -uo pipefail
BASE=/home/oppa-ai/AGi/diagnostic/scorecard/benchmarks
JUDGE=$BASE/grace_canvas_eval/judge_round.py
OUT=$BASE/grace_canvas_eval/results
RENDERS=$BASE/grace_canvas_eval/renders
LOGDIR=$BASE/.logs
ENV=/home/oppa-ai/.venvs/grace-canvas-eval/bin/python
INHIBIT=$BASE/run_with_inhibit.sh
SERVER=/home/oppa-ai/llama.cpp/build/bin/llama-server
PORT=8090
URL=http://127.0.0.1:$PORT/v1
log() { echo "[$(date)] $*"; }

log "Watcher: waiting for round 2 to complete ..."
for i in $(seq 1 1200); do
  if [ -f "$OUT/round2/agents-a1-4b.json" ]; then break; fi
  sleep 60
done
# Make sure the round-2 queue has fully exited before taking the port.
for i in $(seq 1 60); do
  if ! pgrep -f 'bash canvas_round2_vision\.sh' >/dev/null 2>&1; then break; fi
  sleep 10
done
sleep 5
pkill -f 'llama-server.*--port 8090' 2>/dev/null
sleep 5

if [ -f "$OUT/judge-agents-a1-4b.json" ]; then
  log "Judge file already exists, nothing to do."
  exit 0
fi

log "Serving agents-a1-4b with own mmproj as judge ..."
CUDA_VISIBLE_DEVICES=0 setsid nohup "$SERVER" --host 127.0.0.1 --port "$PORT" \
  --log-colors off --n-gpu-layers 999 --flash-attn on \
  --alias agents-a1-4b \
  --model /opt/agi/models/agents-a1-4b/Agents-A1-4B-Q4_K_M.gguf \
  --mmproj /opt/agi/models/agents-a1-4b/Agents-A1-4B-mmproj.gguf \
  --jinja --reasoning-effort medium --reasoning-budget 2048 \
  --ctx-size 16384 \
  > "$LOGDIR/judge-agents-server.log" 2>&1 < /dev/null &
SPID=$!
for i in $(seq 1 90); do
  curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
  kill -0 "$SPID" 2>/dev/null || { log "judge server died"; tail -25 "$LOGDIR/judge-agents-server.log"; exit 1; }
  sleep 2
done

log "Judging baseline renders with agents-a1-4b ..."
AGI_REPO=/home/oppa-ai/AGi bash "$INHIBIT" "$ENV" "$JUDGE" \
  --judge-base-url "$URL" --judge-model agents-a1-4b --judge-label agents-a1-4b \
  --renders "$RENDERS" --results "$OUT" --out "$OUT/judge-agents-a1-4b.json" \
  2>&1 | tee -a "$LOGDIR/judge-agents-a1-4b.log"

kill -TERM "$SPID" 2>/dev/null
sleep 3
log "Agent judge done."
