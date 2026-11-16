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
  exercise AIVA's `GraceMemory` database.
- This is still useful as a model/agent baseline. To measure AIVA's existing
  memory accurately, add a separate adapter that replays benchmark history
  through AIVA's chat path and records answers from its configured 8-exchange
  window. Do not label the simulated BFCL memory score as an AIVA memory score.
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

Start the service from this directory:

```bash
cp .env.example .env
# Edit .env: choose a pinned image tag/digest and set a random SEARXNG_SECRET.
docker compose --env-file .env up -d
```

The JSON API format is enabled in `settings.yml` for BFCL. Confirm it responds
before running the evaluation:

```bash
curl 'http://127.0.0.1:8888/search?q=BFCL+benchmark&format=json'
```

For a published score, record the exact image digest, `settings.yml`, enabled
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
git apply /path/to/AGi-scorecard/benchmarks/bfcl_v4/searxng.patch
git apply /path/to/AGi-scorecard/benchmarks/bfcl_v4/aiva-model.patch
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
