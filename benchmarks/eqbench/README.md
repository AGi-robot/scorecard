# EQ-Bench v4 and Creative Writing v3 for Grace

New evaluations use **EQ-Bench v4** for applied emotional/social intelligence
and **Creative Writing v3** for writing quality. Both use the official runners
and LLM judges. Runs are pending: no v4 or writing score has been measured here.
Historical EQ-Bench v2 results remain in `results/eqbench_v2_*.json`, with their
original labels and scoring; they cannot be converted into either new metric.

## Setup and pinned protocols

The shared launcher, `eqbench_run.py`, verifies the official checkout revision
and rejects modified tracked files before forwarding arguments unchanged.
[protocols.json](protocols.json) records the immutable source pins and protocol.
Install each upstream in its own environment **outside this repository**.
Official repositories include substantial reference-result data: allow disk
space for the clone and outputs. Do not discard the reference pool when
reproducing anchored leaderboard ratings.

```bash
# Run from the scorecard repository root. Choose an external workspace.
export EQ_WORK=/path/to/benchmark-workspace
mkdir -p "$EQ_WORK"
git clone https://github.com/EQ-bench/eqbench4.git "$EQ_WORK/eqbench4"
git -C "$EQ_WORK/eqbench4" checkout 93dcb7f5d430433ad49d501e672a98bcff2c9678
git clone https://github.com/EQ-bench/creative-writing-bench.git "$EQ_WORK/creative-writing-bench"
git -C "$EQ_WORK/creative-writing-bench" checkout c7c3ceef54c40a8ae02dc1c2e1a5e40970fe5c0b
```

EQ-Bench v4 needs Python 3.11+ and `uv sync` in its checkout. Copy its
`config.yaml.example` to `config.yaml`, then add the assessed model, persona
model, judges, and summary model under `model_creds`. Endpoints include the
full chat-completions path. Use environment references for API keys.

Creative Writing v3: create a virtual environment in its checkout, install
`requirements.txt`, copy `.env.example` to `.env`, and configure `TEST_API_URL`,
`TEST_API_KEY`, `JUDGE_API_URL`, and `JUDGE_API_KEY`. Follow upstream setup for
NLTK `punkt` and `cmudict`. Keep credentials outside this repository.

## EQ-Bench v4 run

The pinned official protocol uses 120 personas and 16-message conversations.
Its persona model is Gemini 3.1 Pro Preview; pairwise judges are Gemini 3.1 Pro
Preview, GPT-5.5, and Claude Opus 4.6. Claude Opus 4.8 supplies informational
behavioural traits. The final ability rating is anchored across the comparison
pool with confidence intervals; trait scores do not enter that rating.

```bash
# Copy the pinned reference pool into a writable run directory.
# Keep the official checkout clean so validation also works on resume.
cp -a "$EQ_WORK/eqbench4/results" "$EQ_WORK/eq4-results-grace"
python benchmarks/eqbench/eqbench_run.py \
  --suite eqbench-v4 --checkout "$EQ_WORK/eqbench4" \
  --python "$EQ_WORK/eqbench4/.venv/bin/python" -- \
  --evaluated-model YOUR_MODEL_ID \
  --persona-models google/gemini-3.1-pro-preview \
  --pairwise-judges google/gemini-3.1-pro-preview,openai/gpt-5.5,claude-opus-4-6 \
  --pointwise-judges claude-opus-4-8 \
  --parallel 2 --out "$EQ_WORK/eq4-results-grace/grace_ministral3_14b.json" \
  --run-id grace_ministral3_14b --results-dir "$EQ_WORK/eq4-results-grace" --verbose
```

Copy the reference pool only once, before the first run. Use the same output
path and official arguments to resume; do not recopy over completed work. Keep the pinned
reference/anchor pool and export official ratings using upstream commands.
A new isolated comparison pool is a local rating, not the public leaderboard.
Changing the persona or judges creates a distinct evaluation configuration.

## Creative Writing v3 run

The protocol generates 32 prompts × 3 iterations (96 pieces), temperature 0.7
and `min_p=0.1`, with Claude Sonnet 4.6 judging. Confirm the serving endpoint
honours these generation settings; silently dropping `min_p` changes the run.
Use the pinned `creative_bench_runs.zip` and `elo_results.zip` reference pool:
unzip both in the upstream checkout before the first run. Preserve their
hashes, the starting reference pool, and the judge identity with each run.

```bash
python benchmarks/eqbench/eqbench_run.py \
  --suite creative-writing-v3 --checkout "$EQ_WORK/creative-writing-bench" \
  --python "$EQ_WORK/creative-writing-bench/.venv/bin/python" -- \
  --test-model YOUR_MODEL_ID --judge-model claude-sonnet-4-6 \
  --runs-file creative_bench_runs.json \
  --creative-prompts-file data/creative_writing_prompts_v3.json \
  --run-id grace_ministral3_14b --iterations 3 --threads 2 --verbosity INFO
```

The primary metric is official `elo_norm` from `elo_results.json`; retain
rubric scores separately. Reuse the run files to resume according to upstream
behaviour. Back up the initial reference pool before running; the runner updates
it. A different reference pool or judge can change the rating.

## Validation and outputs

Add `--dry-run` **before** the `--` separator to verify the pin and print the
command without API calls. Pass `-- --help` to view each official runner's
arguments after installing its dependencies. The adapter forwards official
options and does not enforce a full-run protocol: changed settings must be
recorded and labeled as such. Concurrency 2 above is conservative; it does not
change the protocol's task or iteration counts.

Keep transcripts, judge outputs, comparison pools, model/server revisions,
configuration, generation settings, dataset/source hashes, and dependency locks
with the run. Never commit secrets or raw model outputs. Retest Ministral and `swift1.5-qwen3.8-27B` separately first; evaluating routed Grace requires running that actual
system. There is no arithmetic conversion from a component score to Grace's
combined performance.

The scorecard aggregator continues to display historical v2 rows. New judged
ratings are read from the official reports until a versioned import adapter is
available; they must not be normalized to percentages or appended to v2 rows.

## Historical v2 reproduction

`eqbench_v2_legacy.py` retains the previous runner and deterministic scorer:

```bash
python benchmarks/eqbench/eqbench_v2_legacy.py http://127.0.0.1:8080/v1 MODEL LABEL
```

Its 171 emotion-intensity questions measure a different ability and use a
different scale from v4 roleplay and writing ratings. Existing results are
preserved for historical comparisons, including the saved chart.

## Official references

- [EQ-Bench v4 source and setup](https://github.com/EQ-bench/eqbench4/tree/93dcb7f5d430433ad49d501e672a98bcff2c9678)
- [EQ-Bench v4 methodology](https://eqbench.com/eqbench4/#eq4About)
- [Creative Writing v3 source and setup](https://github.com/EQ-bench/creative-writing-bench/tree/c7c3ceef54c40a8ae02dc1c2e1a5e40970fe5c0b)
- [Creative Writing leaderboard](https://eqbench.com/creative_writing.html)
