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
- Qwen thinking models run with `chat_template_kwargs.enable_thinking=false`
  (`--think-off`), consistent with every other Grace benchmark: thinking
  traces would pollute format-sensitive scoring and Ministral has no
  thinking mode to match against.
- Official `test_instruction_following_strict` / `_loose` on the results.

## Running it

```bash
# install the official evaluator's Python dependencies once
python -m pip install -r requirements.txt

# one model at a time (or several servers in parallel, one runner each)
python ifeval_run.py http://127.0.0.1:8080/v1 ministral-3-14b-instruct-2512 ministral3-14b
python ifeval_run.py http://127.0.0.1:8094/v1 swift swift15-qwen3.8-27b --think-off
python ifeval_run.py http://127.0.0.1:8101/v1 a1-4b agents-a1-4b --think-off
python ifeval_run.py http://127.0.0.1:8102/v1 minicpm minicpm5-2b
python ifeval_run.py http://127.0.0.1:8103/v1 neo neohorse-1-4b --think-off
```

Resumable: completed responses are appended to
`results/responses_<label>.jsonl`, so an interrupted run picks up where it
left off. Score files land at `results/ifeval_<label>.json`.

If a run reports that NLTK's `punkt` tokenizer data is missing, install it
once with `python -m nltk.downloader punkt`.

## Why not IFBench

IFBench tests the same underlying skill (harder constraints, newer set) but
there is no published, comparable leaderboard number to anchor against, and
running both doubles GPU time for one decision. IFEval's published scores
let us sanity-check our harness against the field.
