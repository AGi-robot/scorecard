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
tools, or system prompt; temperature 0, top_p 1, one completion. Defaults are
4096 output tokens and a 600-second request timeout for model names containing
`ministral`; Swift and other names use 8192 tokens and 1200 seconds. These
budgets are chosen before generation and can be overridden with `--max-tokens`
and `--request-timeout`. The paper leaves the token budget model-dependent;
record `--max-tokens` and the model server revision with a score. Models must
return final answer text in `message.content`; no custom reasoning stripping
is applied. Configure the server to separate reasoning into `reasoning_content`
(for llama.cpp, `--reasoning-format deepseek`). The runner archives that field
but scores only `message.content`. Thinking mode is a recorded run choice;
`--think-off` is not required by IFBench.

When the API reports `finish_reason=length`, keep its returned answer unchanged
and continue. The official verifier scores that text normally; hitting the cap
does not automatically fail every constraint. An empty final answer, including
a reasoning-only response, is scored as empty. A request timeout closes the
client connection, records an empty answer with `finish_reason=timeout`, and
continues. Timeouts can reflect serving problems as well as slow generation:
report their count alongside accuracy rather than interpreting them as pure
model capability. Non-streaming requests cannot recover text after a timeout.
The timeout is the HTTP socket timeout, not a precise wall-clock generation
deadline. Use the model's normal end tokens and a server-side output cap; do
not set ignore-EOS or use context shifting to extend a request indefinitely.

This follows the pinned upstream `generate_responses.py`, which retains returned
content without requiring a natural stop and records request errors as empty
responses. Our timeout policy is explicit in the run manifest. Prompts and
official scoring remain unchanged. There is no best-of selection or retry of
a capped answer. All questions, including empty answers, stay in the denominator.

Scoring calls the pinned `evaluation_lib` strict/loose functions and registry;
no verifiers are copied or rewritten. Null padding in dataset kwargs is removed
before scoring, matching the official strict evaluator's normalization. Primary
metric is **prompt-level loose accuracy**, as in the paper; summaries also retain
prompt strict and instruction strict/loose accuracy as fractions. The scorecard
displays percentages and keeps this suite separate from IFEval.

Each output directory contains `manifest.json` (dataset hash, revision, model,
endpoint, decoding, timeout and generation policy), `responses.jsonl`, official per-example strict
and loose judgments, and `summary.json`. Keep this directory as the run artifact.
Do not put credentials in the endpoint URL. `OPENAI_API_KEY` is never recorded.
Response records include finish reason, token usage when supplied, elapsed time,
and separately returned reasoning. The summary and scorecard disclose token-cap
and timeout counts. Responses resume only with identical flags/configuration,
including timeout; saved capped and timed-out attempts are not regenerated.
Other HTTP and connection failures stop generation for later resumption.
`--stage generate` and
`--stage score` separate the steps; use the same model, URL, and decoding flags
for both. `--limit N` creates a smoke subset, excluded from the scorecard.

For Ministral and Swift, run one model server at a time with one request slot.
Size its context for the longest prompt plus the selected output budget, and
leave VRAM headroom. Server context is separate from `--max-tokens`.
With a server already serving the corresponding model, from the scorecard root:

```bash
.venv/bin/python benchmarks/ifbench/ifbench_run.py \
  --base-url http://127.0.0.1:8095/v1 --model ministral-3-8b-instruct-2512-abliterated \
  --output benchmarks/ifbench/results/ministral-bounded

.venv/bin/python benchmarks/ifbench/ifbench_run.py \
  --base-url http://127.0.0.1:8095/v1 --model swift15-qwen3.8-27b-local \
  --output benchmarks/ifbench/results/swift-bounded
```

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

