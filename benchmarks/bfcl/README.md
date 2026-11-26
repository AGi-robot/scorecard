# BFCL V4: full function-calling and agentic evaluation

The active BFCL evaluation is the official V4 protocol. It covers single-turn,
multi-turn, live execution, agentic memory and web search, hallucination
measurement, and format sensitivity. Use the pinned official harness and report
its overall and component metrics from the same V4 run. A partial category run
is diagnostic and must not be presented as the complete V4 score.

The repository's bundled V3 runner and existing V3 results are retained only
for historical reference. They are not the active BFCL test and cannot be
converted into V4 scores. Replace the displayed V3 score only after a complete
V4 run is available. The Mind recent-window adapter remains a separate custom
track; it is not part of the official BFCL overall score.

## Historical V3 results

The V3 runner, local scorer, and bundled V3 task data have been removed. Existing V3 response and score artifacts are retained as historical results until a complete V4 result is available. They are not inputs to the active V4 evaluation and cannot be relabeled as V4.

## Official BFCL V4 run

Use BFCL's official full V4 categories via its pinned harness. The following
task tracks make up the current benchmark: It uses the official BFCL task set and evaluator, with a
local SearXNG service replacing the upstream SerpAPI search backend. Scores from
this SearXNG run are **not directly comparable** to leaderboard results using
SerpAPI; report the search backend and versions with every run.

## Official BFCL memory versus Mind's conversation window

The official BFCL harness simulates its `memory_kv`, `memory_vector`, and
`memory_rec_sum` tools. Those categories measure the model/agent against BFCL's
simulator; they do not test Grace's persistent conversation store. Therefore:

- Use [`mind_memory_run.py`](mind_memory_run.py) for the separate Mind
  recent-window track. It uses Mind's public `ConversationStore` API, replays
  BFCL prerequisite dialogue through the configured OpenAI-compatible model
  endpoint, then answers memory questions with the recent context returned by
  Mind and the official BFCL answer checker. It defaults to an 8-exchange
  window and a bare model prompt. Each scenario uses a temporary SQLite file;
  the runner neither launches nor imports Grace's runtime.
- This adapter measures Mind's conversation-history window, not the official
  BFCL memory-tool benchmark. Keep its score separate from `memory_kv`,
  `memory_vector`, and `memory_rec_sum` results.
- BFCL's SearXNG integration below belongs to the official BFCL harness. It is
  independent of Grace's search or chat implementation.

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
- Patches: [`searxng-v4.patch`](searxng-v4.patch) and
  [`aiva-model-v4.patch`](aiva-model-v4.patch), applied from the Gorilla repository root.
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
git apply /path/to/AGi-scorecard/benchmarks/bfcl/searxng-v4.patch
git apply /path/to/AGi-scorecard/benchmarks/bfcl/aiva-model-v4.patch
```

The patch reads `SEARXNG_BASE_URL` (default `http://127.0.0.1:8888`) and
`SEARXNG_LANGUAGE` (default `en`). It preserves BFCL's `title`, `href`, and
`body` result fields. The no-snippet category still fetches result pages from
the BFCL process, so that machine needs outbound access to the selected result
URLs as well as to SearXNG. The SearXNG service does not need to run on the same
host if the BFCL process can reach it; use the appropriate service DNS name
when BFCL itself runs in a container.

## Run V4 categories

The model patch registers the AIVA served model alias
`ministral-3-8b-instruct-2512-abliterated`. For the OpenAI-compatible endpoint, set
`REMOTE_OPENAI_BASE_URL`, `REMOTE_OPENAI_API_KEY`, and
`REMOTE_OPENAI_TOKENIZER_PATH` to the Ministral tokenizer ID or local tokenizer
path. Set `BFCL_PROJECT_ROOT` to a results directory outside this scorecard
checkout.

With the model server already running, point the upstream OSS handler at it
and run the lightweight key-value memory baseline. BFCL simulates this memory
tool backend; it is not Mind's SQLite conversation store:

```bash
export REMOTE_OPENAI_BASE_URL=http://127.0.0.1:8080/v1
export REMOTE_OPENAI_API_KEY=EMPTY
export REMOTE_OPENAI_TOKENIZER_PATH=mistralai/Ministral-3-8B-Instruct-2512
export BFCL_PROJECT_ROOT=/path/to/results/bfcl-v4
bfcl generate --model AGi/ministral-3-8b-instruct-2512-abliterated --test-category memory_kv --skip-server-setup
bfcl evaluate --model AGi/ministral-3-8b-instruct-2512-abliterated --test-category memory_kv
```

After that works, `--test-category memory` runs the full key-value, vector, and
recursive-summary categories. The vector category downloads an embedding model
and uses FAISS, so it has extra package, disk, and memory requirements.

Then run web search against the local SearXNG backend:

```bash
export SEARXNG_BASE_URL=http://127.0.0.1:8888
export SEARXNG_LANGUAGE=en
bfcl generate --model AGi/ministral-3-8b-instruct-2512-abliterated --test-category web_search --skip-server-setup
bfcl evaluate --model AGi/ministral-3-8b-instruct-2512-abliterated --test-category web_search
```

For a first short run, use the upstream CLI's `--run-ids` workflow and a
`test_case_ids_to_generate.json` containing selected IDs. Keep the exact IDs,
model alias, endpoint/model revision, upstream BFCL commit, SearXNG image
revision/settings, and raw outputs together. Do not combine these results with
BFCL V3 AST accuracy or upstream SerpAPI scores into one number.

## Run the Mind recent-window memory track

The runner loads `ConversationStore` from the Mind checkout specified on the
command line, and sends model requests directly to an OpenAI-compatible
endpoint. It does not launch or call Grace's runtime API, and does not load a
persona by default. A frozen prompt snapshot can be supplied explicitly for a
separate configured run. Each scenario uses a temporary SQLite file. Seed
replies are cached under `results/seed_cache/` to resume without repeating
completed prerequisite turns. Use a new `--label` when the model, endpoint,
prompt, or memory window changes.

The pinned Gorilla and Mind checkouts are required. Start the model endpoint,
then from the scorecard root run:

```bash
python benchmarks/bfcl/mind_memory_run.py \
  --mind-root /path/to/AGi-Robot/mind \
  --bfcl-root /tmp/gorilla-bfcl/berkeley-function-call-leaderboard \
  --base-url http://127.0.0.1:8080/v1 \
  --model ministral-3-8b-instruct-2512-abliterated \
  --memory-turns 8 \
  --label ministral3-8b-abliterated-memory8 \
  --limit 5
```

The runner writes per-question results and a summary under
`benchmarks/bfcl/results/v4/`. A limited question run still replays the full
prerequisite history for the selected scenario so it measures the configured
memory window. The summary records source/data/configuration hashes, and the
runner rejects incompatible resumes. It reports BFCL-answer-checker accuracy for this
Mind-specific track; do not present it as the official BFCL `memory` category
score.

## V4 run sequence for Grace

1. Run the official BFCL V4 standard categories together to obtain the current overall score. Then inspect category-level outcomes. It
   uses BFCL's simulator, not Mind's persistent conversation store.
2. Run memory and web-search categories using their official prerequisites and the pinned local SearXNG instance described above. Record any changed backend because SearXNG results differ from leaderboard SerpAPI.
3. Preserve the V4 overall and component results. Report the Mind recent-window adapter separately because it measures another component.

## Native SearXNG alternative

If Docker is unavailable, install and run SearXNG using its
[official installation guide](https://docs.searxng.org/admin/installation.html).
Enable the `json` response format, bind it to a trusted local interface, and
set `SEARXNG_BASE_URL` to the reachable `/` base URL. The BFCL adapter is the
same for Docker and native installs. Record the SearXNG version, settings, and
enabled engines in either case.
