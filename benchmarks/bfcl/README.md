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


---

# BFCL V4: memory and web search

This guide adds BFCL V4's official `memory` and `web_search` categories to the
scorecard workflow. It uses the official BFCL task set and evaluator, with a
local SearXNG service replacing the upstream SerpAPI search backend. Scores from
this SearXNG run are **not directly comparable** to leaderboard results using
SerpAPI; report the search backend and versions with every run.

## Important: AIVA's current memory is a different capability

In AIVA `dev` commit `25fb7e1`, `GraceMemory` persists SQLite conversation
turns and injects the latest eight exchanges into chat context. It does not
expose BFCL's `memory_kv`, `memory_vector`, or `memory_rec_sum` tools. The official BFCL
harness simulates those memory APIs itself. Therefore:

- Running BFCL `memory_kv`, `memory_vector`, or `memory_rec_sum` measures the
  model/agent against BFCL's own memory tools and simulator; it does **not**
  exercise AIVA's `GraceMemory` implementation. The AIVA-specific runner
  below provides that separate measurement.
- Use [`aiva_memory_run.py`](aiva_memory_run.py) for the separate AIVA
  recent-window track. It imports AIVA's actual `GraceMemory` class, replays
  BFCL's prerequisite dialogue by calling the configured LLM and saving each
  exchange through `add_exchange()`, then answers each BFCL memory question
  using `recent()` and the official BFCL answer checker. It defaults to AIVA's
  current 8-exchange window. It does not change or access the user's live
  `~/.agi` database; each scenario uses a temporary SQLite file.
- This adapter measures AIVA's conversation-history window, not the official
  BFCL memory-tool benchmark. Keep its score separate from `memory_kv`,
  `memory_vector`, and `memory_rec_sum` results.
- In the current AIVA `aiva_chat` node, the WebUI `web_search` flag only prefixes
  the prompt with `/web`; the node does not yet call SearXNG. BFCL's SearXNG
  integration below tests the official BFCL web-search tool path, not AIVA's
  WebUI path.

## SearXNG: use Docker for this baseline

Docker Compose is the recommended option here: it keeps SearXNG's dependencies
out of the host Python/ROS environment, binds the service to localhost, and
makes the image and settings easy to record. Native SearXNG is reasonable if
Docker is unavailable, but offers no meaningful speed advantage for this test;
search and page fetching are network-bound.

Start the service from the repository root:

```bash
cp benchmarks/bfcl/.env.example benchmarks/bfcl/.env
# Edit .env: choose a pinned image tag/digest and set a random SEARXNG_SECRET.
docker compose --env-file benchmarks/bfcl/.env -f benchmarks/bfcl/docker-compose-v4.yml up -d
```

The JSON API format is enabled in `settings-v4.yml` for BFCL. Confirm it responds
before running the evaluation:

```bash
curl 'http://127.0.0.1:8888/search?q=BFCL+benchmark&format=json'
```

For a published score, record the exact image digest, `settings-v4.yml`, enabled
SearXNG engines, and run date. Search results vary with engine availability and
time. Keep this service local; do not expose the benchmark instance to a public
network.

## Prepare the official BFCL harness

Use the official repository at the revision both local patches target:

- Upstream commit: `6ea57973c7a6097fd7c5915698c54c17c5b1b6c8`
- Patches: [`searxng.patch`](searxng.patch) and
  [`aiva-model.patch`](aiva-model.patch), applied from the Gorilla repository root.
  The model patch registers AIVA's local Ministral alias in BFCL's model map
  using its prompt-mode quick-test handler.

Clone the official Gorilla repository, check out the pinned commit, install the
BFCL package, then apply both patches:

```bash
git clone https://github.com/ShishirPatil/gorilla.git /tmp/gorilla-bfcl
cd /tmp/gorilla-bfcl
git checkout 6ea57973c7a6097fd7c5915698c54c17c5b1b6c8
cd berkeley-function-call-leaderboard
python -m pip install -e .
cd ..
git apply /path/to/AGi-scorecard/benchmarks/bfcl/searxng.patch
git apply /path/to/AGi-scorecard/benchmarks/bfcl/aiva-model.patch
```

The patch reads `SEARXNG_BASE_URL` (default `http://127.0.0.1:8888`) and
`SEARXNG_LANGUAGE` (default `en`). It preserves BFCL's `title`, `href`, and
`body` result fields. The no-snippet category still fetches result pages from
the BFCL process, so that machine needs outbound access to the selected result
URLs as well as to SearXNG. The SearXNG service does not need to run on the same
host if the BFCL process can reach it; use the appropriate service DNS name
when BFCL itself runs in a container.

## Run the categories

The model patch registers the AIVA served model alias
`ministral-3-14b-instruct-2512`. For the OpenAI-compatible endpoint, set
`REMOTE_OPENAI_BASE_URL`, `REMOTE_OPENAI_API_KEY`, and
`REMOTE_OPENAI_TOKENIZER_PATH` to the Ministral tokenizer ID or local tokenizer
path. Set `BFCL_PROJECT_ROOT` to a results directory outside this scorecard
checkout.

With the model server already running, point the upstream OSS handler at it
and run the lightweight key-value memory baseline. BFCL simulates this memory
tool backend; it is not AIVA's SQLite implementation:

```bash
export REMOTE_OPENAI_BASE_URL=http://127.0.0.1:8080/v1
export REMOTE_OPENAI_API_KEY=EMPTY
export REMOTE_OPENAI_TOKENIZER_PATH=mistralai/Ministral-3-14B-Instruct-2512
export BFCL_PROJECT_ROOT=/path/to/results/bfcl-v4
bfcl generate --model AGi/ministral-3-14b-instruct-2512 --test-category memory_kv --skip-server-setup
bfcl evaluate --model AGi/ministral-3-14b-instruct-2512 --test-category memory_kv
```

After that works, `--test-category memory` runs the full key-value, vector, and
recursive-summary categories. The vector category downloads an embedding model
and uses FAISS, so it has extra package, disk, and memory requirements.

Then run web search against the local SearXNG backend:

```bash
export SEARXNG_BASE_URL=http://127.0.0.1:8888
export SEARXNG_LANGUAGE=en
bfcl generate --model AGi/ministral-3-14b-instruct-2512 --test-category web_search --skip-server-setup
bfcl evaluate --model AGi/ministral-3-14b-instruct-2512 --test-category web_search
```

For a first short run, use the upstream CLI's `--run-ids` workflow and a
`test_case_ids_to_generate.json` containing selected IDs. Keep the exact IDs,
model alias, endpoint/model revision, upstream BFCL commit, SearXNG image
revision/settings, and raw outputs together. Do not combine these results with
BFCL V3 AST accuracy or upstream SerpAPI scores into one number.

## Run the AIVA recent-window memory track

The AIVA runner reuses the actual `GraceMemory` source file, the AIVA `SOUL.md`,
and the official BFCL V4 memory questions and answer checker. It uses a
separate temporary SQLite file for each scenario. Seed replies are generated
by the same configured model and cached under `results/seed_cache/`; this makes
restarts resumable without repeating completed prerequisite turns. Use a new
`--label` when the model, endpoint, system prompt, or memory window changes.

The pinned Gorilla checkout and AIVA checkout are required. Start the local AIVA
LLM endpoint, then from the scorecard root run:

```bash
python benchmarks/bfcl/aiva_memory_run.py \
  --aiva-root /path/to/AGi-Robot/AIVA \
  --bfcl-root /tmp/gorilla-bfcl/berkeley-function-call-leaderboard \
  --base-url http://127.0.0.1:8080/v1 \
  --model ministral-3-14b-instruct-2512 \
  --memory-turns 8 \
  --label ministral3-14b-memory8 \
  --limit 5
```

The runner writes per-question results and a summary under
`benchmarks/bfcl/results/`. A limited question run still replays the full
prerequisite history for the selected scenario so it measures the configured
memory window. It reports a BFCL-answer-checker accuracy for this AIVA-specific
track; do not present it as the official BFCL `memory` category score.

## Baseline sequence for Grace

1. Start with BFCL `memory_kv` as the lightest BFCL memory-tools baseline. It
   uses BFCL's simulator, not AIVA's eight-exchange chat history.
2. Run `web_search` with the same model and the pinned local SearXNG instance.
3. When AIVA exposes real memory and search tools to its agent loop, rerun the
   same IDs through that agent and compare per-task outcomes. Keep the official
   simulator and the AIVA-backed results as separately labeled tracks until
   their tool interfaces match.

## Native SearXNG alternative

If Docker is unavailable, install and run SearXNG using its
[official installation guide](https://docs.searxng.org/admin/installation.html).
Enable the `json` response format, bind it to a trusted local interface, and
set `SEARXNG_BASE_URL` to the reachable `/` base URL. The BFCL adapter is the
same for Docker and native installs. Record the SearXNG version, settings, and
enabled engines in either case.
