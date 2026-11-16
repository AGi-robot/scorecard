# IFBench single-turn baseline

Uses the official [allenai/IFBench](https://github.com/allenai/IFBench) code
and bundled 300 test prompts at commit
`488918665d53f867fa908a293769ec6e71e74aec`. The multi-turn suite is available through the same runner with `--suite multiturn`;
its protocol and dataset remain distinct from the single-turn suite and from Google IFEval.

Install the shared, pinned CPU client/scorer dependencies from the scorecard root:

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r benchmarks/baseline-requirements.lock
```

Prepare without a model, or generate and score using an OpenAI-compatible endpoint:

```bash
.venv/bin/python benchmarks/ifbench/ifbench_run.py --stage prepare \
  --output benchmarks/ifbench/results/preflight

export OPENAI_API_KEY=EMPTY  # replace for an authenticated endpoint
.venv/bin/python benchmarks/ifbench/ifbench_run.py \
  --base-url http://127.0.0.1:8080/v1 --model MODEL \
  --output benchmarks/ifbench/results/MODEL
```

The runner clones and verifies the official revision automatically. `--official`
can name an existing clean checkout at that revision. `prepare` only downloads
and validates inputs; use a separate output directory for a model run.

Protocol: send the exact prompt as one user message, no persona, memory,
tools, or system prompt; temperature 0, top_p 1, one completion, default
8192 output tokens. The paper leaves the token budget model-dependent;
record `--max-tokens` and the model server revision with a score. Models must
return final answer text in `message.content`; no custom reasoning stripping
is applied. Truncated or missing final text stops the run without a score.

Scoring calls the pinned `evaluation_lib` strict/loose functions and registry;
no verifiers are copied or rewritten. Null padding in dataset kwargs is removed
before scoring, matching the official strict evaluator's normalization. Primary
metric is **prompt-level loose accuracy**, as in the paper; summaries also retain
prompt strict and instruction strict/loose accuracy as fractions. The scorecard
displays percentages and keeps this suite separate from IFEval.

Each output directory contains `manifest.json` (dataset hash, revision, model,
endpoint and decoding), successful `responses.jsonl`, official per-example strict
and loose judgments, and `summary.json`. Keep this directory as the run artifact.
Do not put credentials in the endpoint URL. `OPENAI_API_KEY` is never recorded.
Responses resume only with identical flags/configuration. HTTP failures stop
generation rather than becoming scored empty answers. `--stage generate` and
`--stage score` separate the steps; use the same model, URL, and decoding flags
for both. `--limit N` creates a smoke subset, excluded from the scorecard.

The runner supplies NLTK resources from the official nltk_data commit
`550b6625bcef1f2abff2ff770a5a0d272c9c6b2a` before importing the verifier,
avoiding its automatic moving-resource downloads. Archive the NLTK cache with
the run environment. The Python dependency lock is shared with the other two
integrations. Tests run with:

```bash
.venv/bin/python -m unittest discover -s benchmarks/tests -v
# Also exercise official scorer fixtures after preparing the three datasets:
IFBENCH_OFFICIAL=/path/to/pinned/IFBench LCB_OFFICIAL=/path/to/pinned/LiveCodeBench .venv/bin/python -m unittest discover -s benchmarks/tests -v
```

Code is Apache-2.0; IFBench data is ODC-BY-1.0 with Ai2's usage guidelines and
third-party output terms described in the upstream README. Data, generated
responses, caches, and environments are not vendored here.

Validation here: all 300 pinned inputs prepared; scorer checks use synthetic
fixtures only. **No model score recorded**: no endpoint was configured and local
ports 8000/8080 were unavailable.

## Multi-turn constraint-isolation run

The same runner supports the released fixed-history test suite:

```bash
.venv/bin/python benchmarks/ifbench/ifbench_run.py --suite multiturn \
  --stage prepare --output benchmarks/ifbench/results/multiturn-preflight

.venv/bin/python benchmarks/ifbench/ifbench_run.py --suite multiturn \
  --base-url http://127.0.0.1:8080/v1 --model MODEL \
  --output benchmarks/ifbench/results/multiturn-MODEL
```

It uses dataset `allenai/IFBench_multi-turn`, revision
`e1ea65c5178fbeac522a26d12b8c71a298e9846d`, config `ifbench_constraints`,
split `test` (1387 examples). It sends the released user task, fixed assistant
response, and final user constraint as-is, then generates only the final turn.
The flattened prompt is used only as the official scorer key. Primary metric is
prompt-level loose accuracy. Output paths and scorecard row stay distinct.

For convenience, the old `benchmarks/ifbench_multiturn/ifbench_multiturn_run.py`
path remains as a compatibility wrapper; new runs and docs use `benchmarks/ifbench/`.
