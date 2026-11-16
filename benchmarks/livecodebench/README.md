# LiveCodeBench baseline

Code generation only, using official
[LiveCodeBench](https://github.com/livecodebench/livecodebench) commit
`28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24` and dataset
`livecodebench/code_generation_lite` revision
`0fe84c3912ea0c4d4a78037083943e8f0c4dd505`.

The protocol is **release_v6**, the cumulative May 2023–April 2025 set of
1055 tasks, with no date filter. The runner loads `test.jsonl` through
`test6.jsonl`, matching `ALLOWED_FILES['release_v6']` in the pinned dataset
script. `test6.jsonl` alone would only be the 175-task v6 increment. Immutable
file URLs avoid the official loader's unpinned default revision and moving
`release_latest`. Private/public test decoding, prompt formatting, extraction,
execution checks, and pass@k estimation all use official Python functions.

Install [shared CPU dependencies](../ifbench/README.md), then prepare:

```bash
.venv/bin/python benchmarks/livecodebench/livecodebench_run.py --stage prepare \
  --output benchmarks/livecodebench/results/preflight
```

Generate through an OpenAI-compatible model endpoint:

```bash
export OPENAI_API_KEY=EMPTY
.venv/bin/python benchmarks/livecodebench/livecodebench_run.py --stage generate \
  --base-url http://127.0.0.1:8080/v1 --model MODEL \
  --output benchmarks/livecodebench/results/MODEL
```

Run the **score stage in an isolated disposable container or VM**, with no
credentials, network, or sensitive mounts. The official checker executes model
code in subprocesses and is not a security boundary. Give the scoring environment
the pinned official checkout, Python dependencies, cached dataset, and copied run
directory, then run with the same flags and paths:

```bash
.venv/bin/python benchmarks/livecodebench/livecodebench_run.py --stage score \
  --base-url http://127.0.0.1:8080/v1 --model MODEL \
  --output benchmarks/livecodebench/results/MODEL
```

The score stage makes no model calls. Endpoint metadata identifies the generating
run even if that URL is unreachable in the isolated scorer. Preparation and
generation import official code; use only the official pinned dataset.
Generation uses only question text and starter code; private tests are decoded
only in the score stage. The `all` stage combines generation and execution and
therefore belongs in an isolated evaluation environment too.

Protocol: official `LMStyle.OpenAIChat` prompt and extraction; n=10 independent
samples, temperature 0.2, top_p 0.95, default max_tokens=2000, timeout 6 seconds,
one evaluation worker. Record the actual token budget and model/server revision.
Timeouts and worker count are part of the manifest. This adapter targets chat
models using the official generic chat format; other model-family templates need
a separately labeled protocol. No tools, memory, self-repair, or custom judge.

Artifacts: `manifest.json` with a SHA-256 over the six-file hash index and all protocol settings,
`responses.jsonl` with raw completions, `custom_outputs.json` in official
question_id/code_list format, `official_metrics.json` with per-test results and
metadata, and `summary.json` with official pass@1, pass@5, pass@10 fractions.
All ten successful samples per selected task are required before scoring;
truncation/API failures abort without publishing a score. Resume requires identical
configuration. `--limit` marks a smoke subset and excludes it from the scorecard.

Full-run rows remain separate from EvalPlus, IFBench, and other scenarios.
The scorecard shows pass@1 primary and pass@5 secondary as percentages; scores
over this historical window make no claim about contamination for newer models.
Upstream code and dataset declare MIT licensing; retain upstream notices when
redistributing. No benchmark data or generated programs are committed here.

Validation here: pinned release preparation and synthetic prompt/extraction and
checker fixtures. **No model score recorded** because no endpoint was available.
