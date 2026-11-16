# BFCL for Grace (single-turn AST categories)

Tool-calling accuracy on the official Berkeley Function Calling Leaderboard
data, scored with AST matching that follows the official checker's semantics.

## Scope (deliberate)

Only the five single-turn, AST-checkable categories are run here:

| Category | n | What it probes |
|---|---|---|
| `simple` | 400 | one function, correct name + arguments |
| `multiple` | 200 | pick the right function among several, correct args |
| `parallel` | ~130 | several calls in one turn (order-insensitive) |
| `parallel_multiple` | ~200 | several calls, chosen among distractors |
| `irrelevance` | 240 | must NOT call any function |

Excluded on purpose: `live_*` (needs user-contributed execution), `multi_turn_*`
(needs the state simulators), `memory_*` / `web_search_*` (need live backends —
tracked separately, see below), `executable` / `REST` / `SQL` / `java` /
`javascript` (language runtimes Grace never calls).

Data: `gorilla-llm/Berkeley-Function-Calling-Leaderboard`, branch `main`
(Apache-2.0). Questions from `BFCL_v3_<cat>.json`, answers from
`possible_answer/BFCL_v3_<cat>.json`, copied into `data/`.

## Protocol

- temperature 0.0, `max_tokens` 1024, raw user message (no system prompt).
- Tools passed as OpenAI `tools` (converted from BFCL's `dict`-style schemas).
- Prediction read from `message.tool_calls[].function.{name,arguments}`.
- Think-off for thinking models, matching every other bench in this repo.

## Scorer semantics (`bfcl_scoring.py`)

Dependency-free reimplementation of the official AST checker
(`bfcl_eval/eval_checker/ast_eval/ast_checker.py`, Apache-2.0 — vendoring the
full file was skipped because it drags in the whole `bfcl_eval` package tree;
the semantics below were ported instead):

- Function name must match exactly.
- Every ground-truth argument with a non-empty allowed list must be present,
  unless `""` is in its allowed list (optional argument — may be omitted, and
  an explicit `""` is accepted as omitted).
- Each provided value must equal one of the allowed values, type-leniently
  (`10 == 10.0`, `"true"` accepted for booleans, nested structures compared
  normalized). Numeric tolerance 1e-6.
- `parallel` / `parallel_multiple` are order-insensitive; call count must match.
- `irrelevance` passes only with zero tool calls.

Validated by `bfcl_scoring.py` self-test plus a ground-truth round-trip:
feeding the first allowed answer back as the prediction scores 20/20 on all
four answer-bearing categories, empty predictions score 0, wrong names score 0.

## Running it

```bash
python bfcl_run.py http://127.0.0.1:8080/v1 ministral-3-14b-instruct-2512 ministral3-14b --think-off
# --categories "simple parallel"  to subset
# --limit N                       to smoke-test
```

Resumable: completed answers append to `results/responses_<label>.jsonl`
(keyed on prompt id, like the IFEval runner). Score file lands at
`results/bfcl_<label>.json`.

## BFCL V4 memory and web search

This runner remains a BFCL V3 single-turn baseline. To evaluate the agent loop,
use the [official BFCL repository](https://github.com/ShishirPatil/gorilla/tree/main/berkeley-function-call-leaderboard)
and its maintained `bfcl-eval` harness for V4 `memory` and `web_search`.
Those categories use multi-turn tool simulations and answer evaluation, so their
scores are not directly comparable with the AST scores above. BFCL's memory
simulation does not query Grace's PostgreSQL memory, and its web-search setup
does not measure Grace's own search service. Treat them as agent/tool-use
capability checks; build a separate adapter before claiming end-to-end product
coverage.

Follow the upstream installation and model-registration instructions for the
exact harness revision. Remote OpenAI-compatible endpoints and web-search
credentials are configured by that harness; do not put API keys in this repo.
The upstream model handler and simulator requirements can change between
releases, so record the pinned `bfcl-eval` version, categories, model alias,
endpoint, and external search provider with each result. Keep the V3 runner and
results here as the reproducible single-turn baseline.
