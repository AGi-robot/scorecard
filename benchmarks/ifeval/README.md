# IFEval for Grace

Instruction-following accuracy on the 540 official `google/IFEval` prompts,
scored with the official google-research scoring code (vendored under
`official/`, Apache-2.0 — same license as the dataset). Reports both
**strict** and **loose** accuracy, exactly like the published leaderboard.

## Why this one matters for Grace

IFEval is the closest standard bench to Grace's daily job: following
explicit formatting constraints. SOUL demands an emoji + colon prefix and
1–2 sentences; `canvas_draw` demands valid JSON tool calls with exact point
counts. A model that can't follow "write more than 400 words" or "mention
AI at least 3 times" won't follow Grace's output contracts either.

## Protocol

- temperature 0.0, max_tokens 2048, plain user message (no system prompt —
  matches the official harness, which sends the raw prompt).
- IFEval itself does not prescribe a thinking mode or reasoning-effort level;
  it scores the generated response text. Scorecard uses each model's
  normal-task policy: Swift runs with `reasoning_effort=low`, while Ministral
  uses its standard generation mode.
- Use `--think-off` only for a separately labeled comparison variant. The
  runner records this setting and prevents checkpoints from mixing modes.
  Reasoning effort is also recorded in the checkpoint fingerprint.
- Official `test_instruction_following_strict` / `_loose` on the results.

## Running it

```bash
# install the official evaluator's Python dependencies once
python -m pip install -r requirements.txt

# Run one model per process. API model IDs may differ from scorecard labels; this keeps the endpoint ID `swift`
# but labels its output files with the exact Swift 1.5 Qwen 3.8 27B build.
python ifeval_run.py http://127.0.0.1:8080/v1 ministral-3-8b-instruct-2512-abliterated ministral3-8b-abliterated
python ifeval_run.py http://127.0.0.1:8094/v1 swift swift1.5-qwen3.8-27B-low --reasoning-effort low
python ifeval_run.py http://127.0.0.1:8101/v1 a1-4b agents-a1-4b
python ifeval_run.py http://127.0.0.1:8102/v1 minicpm minicpm5-2b
python ifeval_run.py http://127.0.0.1:8103/v1 neo neohorse-1-4b
```

Resumable: completed responses are appended to
`results/responses_<label>.jsonl`, so an interrupted run picks up where it
left off. Resume requires the same model, endpoint, dataset, limit, and
thinking settings. Use a fresh label for older checkpoints or when changing
these settings. A full score is written to `results/ifeval_<label>.json`
only once every response is present. A limited run writes
`results/ifeval_smoke_<label>.json`.

If a run reports that NLTK's `punkt` tokenizer data is missing, install it
once with `python -m nltk.downloader punkt`.

## Why not IFBench

IFBench tests the same underlying skill (harder constraints, newer set) but
there is no published, comparable leaderboard number to anchor against, and
running both doubles GPU time for one decision. IFEval's published scores
let us sanity-check our harness against the field.
