#!/bin/bash
# After the judge-only script finishes (it skips round 2 via dummy files),
# remove the dummies and launch the vision round 2.
set -uo pipefail
BASE=/home/oppa-ai/AGi/diagnostic/scorecard/benchmarks
OUT=$BASE/grace_canvas_eval/results
log() { echo "[$(date)] $*"; }

log "Watcher: waiting for judge-deepseek-9b.json ..."
for i in $(seq 1 600); do
  if [ -f "$OUT/judge-deepseek-9b.json" ] && \
     python3 -c "import json;d=json.load(open('$OUT/judge-deepseek-9b.json'));exit(0 if d.get('n',0)>=56 and not d.get('partial') else 1)" 2>/dev/null; then
    break
  fi
  sleep 30
done

log "Judges complete. Waiting for old script to exit ..."
for i in $(seq 1 60); do
  if ! pgrep -f 'bash canvas_round2\.sh' >/dev/null 2>&1; then break; fi
  sleep 10
done
# Belt and suspenders: kill any stragglers of the old script only.
for pid in $(pgrep -f 'bash canvas_round2\.sh' 2>/dev/null); do
  if ! tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null | rg -q 'vision'; then
    kill -TERM "$pid" 2>/dev/null
  fi
done
sleep 5
pkill -f 'llama-server.*--port 8090' 2>/dev/null
sleep 5

log "Removing dummy skip files ..."
rm -f "$OUT/round2/"*.json
ls "$OUT/round2/" 2>/dev/null || log "round2/ empty, clean"

log "Launching vision round 2 ..."
cd "$BASE" && setsid nohup bash canvas_round2_vision.sh > .logs/canvas-round2-vision.log 2>&1 < /dev/null &
log "Vision round 2 launched."
