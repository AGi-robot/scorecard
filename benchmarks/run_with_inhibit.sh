#!/bin/bash
# Run a command with systemd-inhibit blocking sleep/shutdown/hibernate.
# Usage: ./run_with_inhibit.sh <command...>
set -euo pipefail

if ! command -v systemd-inhibit >/dev/null 2>&1; then
  echo "systemd-inhibit not found; running without inhibitor" >&2
  "$@"
  exit $?
fi

echo "[$(date)] Holding shutdown/sleep inhibitor for: $*"
systemd-inhibit \
  --what=shutdown:sleep \
  --who=benchmarks \
  --why="Long-running benchmark (IFEval/canvas eval) in progress; do not suspend or power off" \
  --mode=block \
  "$@"
