#!/usr/bin/env bash
# Grace benchmark launcher — pick a test, it runs the TWO Modal servers.
# Env is handled here: sources ~/.config/agi/modal-bench.env itself.
set -euo pipefail
cd "$(dirname "$0")"
AGI_ROOT="$(cd ../.. && pwd)"

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
MODAL_MINISTRAL_MODEL="$(python3 -c 'from run_modal_bench import MINISTRAL_ALIAS; print(MINISTRAL_ALIAS)')"
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

MODEL_SEL=""
for a in "$@"; do
  case "$a" in
    --model=*) MODEL_SEL="${a#--model=}";;
  esac
done
ARGS=()
for a in "$@"; do
  [[ "$a" == --model=* ]] || ARGS+=("$a")
done
if [[ -z "$MODEL_SEL" ]]; then
  echo "Models: [both]/ministral/swift (benchmark-only Modal endpoints)"
  read -rp "Models [both]: " MODEL_SEL
  MODEL_SEL="${MODEL_SEL:-both}"
fi

run_sel() { # $1 = bench, rest = extra args; runs selected models
  local bench="$1"; shift
  for m in ministral swift; do
    if [[ "$MODEL_SEL" != "both" && "$MODEL_SEL" != "$m" ]]; then continue; fi
    echo "### $m (Modal) — $bench"
    local url_var="MODAL_${m^^}_URL"
    preflight "${!url_var}" || return 1
    $RUN --model "$m" --bench "$bench" "$@"
  done
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
    if [[ "$MODEL_SEL" != "both" && "$MODEL_SEL" != "$m" ]]; then continue; fi
    echo "### $m (Modal) — EvalPlus $ds"
    local url_var="MODAL_${m^^}_URL"
    preflight "${!url_var}" || return 1
    $RUN --model "$m" --bench evalplus --dataset "$ds" "$@"
  done
}

run_bfcl() {
  local default_mind_root="$AGI_ROOT/AIVA/mind/memory"
  local default_bfcl_root="/tmp/gorilla-bfcl/berkeley-function-call-leaderboard"
  local mind_root bfcl_root

  read -rp "Mind checkout root [$default_mind_root]: " mind_root
  mind_root="${mind_root:-$default_mind_root}"
  # Accept AIVA/mind too, then resolve to the memory package root.
  if [[ ! -f "$mind_root/src/memory/conversation.py" && \
        -f "$mind_root/memory/src/memory/conversation.py" ]]; then
    mind_root="$mind_root/memory"
  fi
  read -rp "BFCL checkout root [$default_bfcl_root]: " bfcl_root
  bfcl_root="${bfcl_root:-$default_bfcl_root}"

  if [[ ! -f "$mind_root/src/memory/conversation.py" ]]; then
    echo "Mind ConversationStore source not found under: $mind_root" >&2
    return 1
  fi
  if [[ ! -d "$bfcl_root/bfcl_eval/data" ]]; then
    echo "BFCL checkout must contain bfcl_eval/data: $bfcl_root" >&2
    return 1
  fi

  run_sel bfcl --mind-root "$mind_root" --bfcl-root "$bfcl_root" "${ARGS[@]}"
}

echo "Grace benchmark launcher — both Modal servers, env loaded."
echo "-- OFFICIAL STANDARDS --"
echo "1) IFEval [541 prompts, official scoring]"
echo "2) IFBench [AllenAI, pinned]"
echo "3) LongMemEval [ICLR 2025, 500Q]"
echo "4) BFCL V4 memory component [prompts for Mind and BFCL checkout paths]"
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
  1) run_sel ifeval "${ARGS[@]}" ;;
  2) run_sel ifbench "${ARGS[@]}" ;;
  3) run_sel longmemeval "${ARGS[@]}" ;;
  4) run_bfcl ;;
  5) run_sel livecodebench "${ARGS[@]}" ;;
  6) run_evalplus humaneval "${ARGS[@]}" ;;
  7) run_evalplus mbpp "${ARGS[@]}" ;;
  8) $RUN --model ministral --bench eqbench ;;
  9) run_sel canvas --task T1-lighthouse "${ARGS[@]}" ;;
  10) run_sel canvas "${ARGS[@]}" ;;
  11) chat_generate ;;
  12) $CHAT rate ;;
  13) $CHAT score ;;
  *) echo "bye." ;;
esac
