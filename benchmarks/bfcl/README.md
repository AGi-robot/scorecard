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

The BFCL V4 setup, SearXNG adapter, Docker configuration, run commands, and
AIVA memory limitations are documented in the [BFCL V4 guide](v4/README.md).
This V3 runner remains the local single-turn AST baseline.
