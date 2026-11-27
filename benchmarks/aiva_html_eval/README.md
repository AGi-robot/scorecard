# AIVA HTML cartoon coding comparison

A custom, single-task coding comparison: each contestant receives the identical
architecture snapshot and writes one self-contained interactive cartoon HTML
explainer. This tests one-shot HTML coding, not a tool-using autonomous agent.
No score is added to REPORT_CARD.md.

The prompt describes the source-level implementation in AIVA/README.md and
AIVA/docs/telepathy-flow.md. It distinguishes SQLite recent history from semantic
retrieval, reversible Cypher encoding from encryption, optional Canvas/MOSS from
text chat, and AIVA from AuRoRA. It is not a claim about live process health.

## Run

Python 3 plus Playwright and its Chromium browser are required for checks.
The existing environment already has these; no AIVA dependency changes needed.

From the AGi repository root, compare already running servers:

```sh
python3 diagnostic/scorecard/benchmarks/aiva_html_eval/aiva_html_eval.py generate \
  --output diagnostic/scorecard/benchmarks/aiva_html_eval/results/cartoon-v1 \
  --contestant nymphaea-rp=http://127.0.0.1:8080/v1/nymphaea-rp
```

Repeat --contestant for other endpoints. This may queue behind their current
requests. Each model gets temperature 0.7, top_p 0.95, seed 42 (if supported by
the backend), and 6144 output tokens. Reasoning counts toward the backend's
output limit. Endpoint mode preserves the existing server settings.

For all ten installed chat/code checkpoints, run an isolated sequential sweep:

```sh
python3 diagnostic/scorecard/benchmarks/aiva_html_eval/aiva_html_eval.py sweep \
  --output diagnostic/scorecard/benchmarks/aiva_html_eval/results/cartoon-v1 \
  --wait-for-idle
```

The sweep starts only its own llama.cpp child on port 8096, checks readiness,
generates a page, stops that exact child, then advances. It never kills existing
servers. It waits when known IFEval/IFBench/EvalPlus generation jobs are active.
It does not reserve GPUs: avoid starting a different benchmark during the sweep.
All sweep contestants use the same llama.cpp engine, 16K context, q4 KV caches,
one slot, automatic GPU layer fitting (CPU offload when necessary), and a 512-token reasoning budget where supported. Nymphaea alone uses
the configured V7-Tekken override; others use embedded templates. Exact server
commands are saved. A rejected architecture or cache configuration is recorded
as a failure, not silently switched to a different engine. Use --models to select
a subset. Voyage embeddings and mmproj vision adapters are not contestants.

Generation resumes completed responses. Use a new output directory after
changing the prompt or generation settings. Run failures produce a nonzero exit
status; per-model artifacts remain available. An occupied port is an error.

Recheck saved pages without spending more inference:

```sh
python3 diagnostic/scorecard/benchmarks/aiva_html_eval/aiva_html_eval.py check \
  --output diagnostic/scorecard/benchmarks/aiva_html_eval/results/cartoon-v1
```

Open results/index.html for the combined original/retry comparison, or
results/cartoon-v1/index.html for the original visual gallery. Each model has
index.html, desktop/mobile screenshots, checks.json, the complete response,
request provenance, timing, token usage, and finish reason. Generated pages are
served to the test browser through intercepted requests with network access
blocked by routing and a content security policy. Gallery previews are sandboxed.
Do not treat generated code as trusted application code or run its commands.

## Retry truncated responses with medium effort

```sh
python3 diagnostic/scorecard/benchmarks/aiva_html_eval/aiva_html_eval.py retry-limited \
  --source diagnostic/scorecard/benchmarks/aiva_html_eval/results/cartoon-v1 \
  --output diagnostic/scorecard/benchmarks/aiva_html_eval/results/cartoon-medium \
  --reasoning-effort medium --reasoning-budget -1 --max-tokens 12288 --wait-for-idle
```

This waits for the original owned sweep, then selects only `finish_reason=length`
responses. Originals remain untouched. It sends `reasoning_effort: medium` and
sets the matching server option. The original 512-token thinking cap is removed,
so the template can apply medium effort. This retry uses up to 12288 output
tokens, as requested; both effort and output allowance differ from the original. Some templates ignore effort levels; this is a requested setting,
not proof that a model changed its reasoning. The larger output budget is a
separate setting from medium effort. `retry-plan.json` records the selected models and configuration.

## What the checks mean

Sixteen mechanical checks cover a nonempty page, initial state, visible
controls, seven advancing steps, changing labels, end clamping, reset,
play/pause, actual autoplay advancement, reset cancellation, automatic end stopping, mobile overflow/controls, JavaScript errors, and external requests.
Tests exercise the stated window.AIVA_DEMO API and real DOM buttons. When a
required button ID is missing, the API is checked independently and the control
contract still fails; a selector mismatch does not suppress all behavior checks. Missing
checks count as failures. A truncated response is recorded separately; passing
some checks does not make truncated generation a successful completion.

Aesthetic quality and factual correctness are **not** scored automatically.
Compare screenshots and pages for: cartoon clarity, visual hierarchy, animation,
readability, accurate component boundaries and message direction, truthful
memory/tool claims, and optional capabilities kept separate. These observations
are subjective and should be reported separately from mechanical checks. One
sample per model does not establish a stable model ranking.
