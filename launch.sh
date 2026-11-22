#!/usr/bin/env bash
# Grace benchmark launcher — pick a test, it runs the TWO Modal servers.
# Env is handled here: sources ~/.config/agi/modal-bench.env itself.
set -euo pipefail
cd "$(dirname "$0")"

ENV_FILE="$HOME/.config/agi/modal-bench.env"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
fi
if [[ -z "${OPENAI_API_KEY:-}" && -n "${AIVA_LLM_API_KEY:-}" ]]; then
  export OPENAI_API_KEY="$AIVA_LLM_API_KEY"
fi
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "No API key. Put it in $ENV_FILE (see modal-bench setup) and rerun."
  exit 1
fi

MODAL_MINISTRAL_URL="https://oppa-ai-org--grace-llm-serve-serve-ministral.us-east.modal.run/v1"
MODAL_MINISTRAL_MODEL="ministral-3-14b-instruct-2512"
MODAL_SWIFT_URL="https://oppa-ai-org--grace-llm-serve-serve-swift.us-east.modal.run/v1"
MODAL_SWIFT_MODEL="swift15-qwen3.8-27b-local"
RUN="python3 run_modal_bench.py"
CHAT="python3 benchmarks/grace_chatbot_eval/preference_bench.py"

preflight() {
  local url="$1"
  if ! curl -sL -o /dev/null -w "%{http_code}" --max-time 120 \
      -H "Authorization: Bearer $OPENAI_API_KEY" "$url/health" | grep -q 200; then
    echo "!! $url not healthy (cold-start can take 10+ min on first touch)."
    read -rp "Keep waiting and retry? [y/N] " yn
    [[ "$yn" =~ ^[Yy]$ ]] || return 1
    preflight "$url"
  fi
}

run_both() { # $1 = bench, rest = extra args passed to run_modal_bench.py
  local bench="$1"; shift
  echo "### ministral (Modal) — $bench"
  preflight "$MODAL_MINISTRAL_URL" || return 1
  $RUN --model ministral --bench "$bench" "$@"
  echo "### swift (Modal) — $bench"
  preflight "$MODAL_SWIFT_URL" || return 1
  $RUN --model swift --bench "$bench" "$@"
}

chat_generate() {
  echo "Variant: [a] original scripts = standard Arena setup (default)"
  echo "         [b] alternate wordings  [alternate] random per play (anti-memorization)"
  read -rp "Variant [a]: " variant
  variant="${variant:-a}"
  read -rp "Limit to script ids (space-separated, empty = all 6): " scripts
  local script_args=()
  for s in $scripts; do script_args+=(--script "$s"); done
  preflight "$MODAL_MINISTRAL_URL" || return 1
  $CHAT generate \
    --contestant "ministral=$MODAL_MINISTRAL_URL/$MODAL_MINISTRAL_MODEL" \
    --contestant "swift=$MODAL_SWIFT_URL/$MODAL_SWIFT_MODEL" \
    --variant "$variant" "${script_args[@]}"
}

run_evalplus() { # $1 = dataset
  local ds="$1"; shift
  for m in ministral swift; do
    echo "### $m (Modal) — EvalPlus $ds"
    local url_var="MODAL_${m^^}_URL"
    preflight "${!url_var}" || return 1
    $RUN --model "$m" --bench evalplus --dataset "$ds" "$@"
  done
}

echo "Grace benchmark launcher — both Modal servers, env loaded."
echo "-- OFFICIAL STANDARDS --"
echo "1) IFEval [541 prompts, official scoring]"
echo "2) IFBench [AllenAI, pinned]"
echo "3) LongMemEval [ICLR 2025, 500Q]"
echo "4) BFCL [aiva v4 harness]"
echo "5) LiveCodeBench [pinned rev]"
echo "6) EvalPlus HumanEval+"
echo "7) EvalPlus MBPP+"
echo "8) EqBench (guided: needs checkout + judges)"
echo ""
echo "-- GRACE CUSTOM --"
echo "9) Canvas lighthouse [protocol v4]"
echo "10) Canvas full suite [protocol v4]"
echo "11) Chat generate (both contestants)"
echo "12) Chat rate (blind pairwise, interactive)"
echo "13) Chat score (win rates + Elo)"
read -rp "Choice: " choice
case "$choice" in
  1) run_both ifeval "$@" ;;
  2) run_both ifbench "$@" ;;
  3) run_both longmemeval "$@" ;;
  4) run_both bfcl "$@" ;;
  5) run_both livecodebench "$@" ;;
  6) run_evalplus humaneval "$@" ;;
  7) run_evalplus mbpp "$@" ;;
  8) $RUN --model ministral --bench eqbench ;;
  9) run_both canvas --task T1-lighthouse "$@" ;;
  10) run_both canvas "$@" ;;
  11) chat_generate ;;
  12) $CHAT rate ;;
  13) $CHAT score ;;
  *) echo "bye." ;;
esac
