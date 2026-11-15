# EQ-Bench v2 for Grace

Emotional-intelligence screen: 171 scenarios, each asking the model to rate
the intensity (0–10) of four emotions a character would feel. Scored
deterministically against reference answers with the official
`lib/scoring.py` (vendored here as `eqbench_scoring.py`, MIT — see
`LICENSE.EQ-Bench-MIT`; questions from the EQ-Bench repo's
`data/eq_bench_v2_questions_171.json`).

## Protocol and scoring

Uses the official EQ-Bench v2 full-scale scorer on the model's raw 0–10
ratings (no normalization to sum to 10). The run uses temperature 0.01,
`max_tokens=60`, up to 3 attempts per question until the answer parses, and
no-revise mode. The runner saves raw parsed ratings alongside per-question
scores. Scores use the same v2 scoring function as the published leaderboard;
generation settings and serving stack can still affect comparisons.

## Running it

```bash
# point at any OpenAI-compatible endpoint (a llama-server router works)
python eqbench_run.py http://127.0.0.1:8080/v1 ministral-3-14b-instruct-2512 ministral3-14b
python eqbench_run.py http://127.0.0.1:8081/v1 swift swift15-qwen3.8-27b
# results land in results/eqbench_v2_<label>.json
```

The `eqbench_v2_` prefix keeps these full-scale results separate from older
runs that used EQ-Bench's legacy normalized (v1) scoring. Existing result files
are not rewritten; those scores cannot be converted to v2 without the original
raw emotion ratings.

~15–30 min per model on a 3060 (171 short generations + test executions).

## Why v2 and not v4

EQ-Bench v4 grades multi-turn roleplays with an **LLM judge**, which makes
the judge the measurement instrument: judging emotional intelligence
requires emotional intelligence, so the judge must be at least as strong
as the models under test. Using one of the contestants as judge is
circular; using an API judge breaks the local-only principle and costs
money. v2's reference-scored intensity ratings need no judge, run
deterministically, and match the published leaderboard — the right screen
for companion candidates. Revisit v4 only if a judged active-EQ signal is
ever needed (e.g. round-robin judging where every model judges all, costs
permitting).

## What it measures (and doesn't)

EQ-Bench v2 measures emotion *recognition* — predicting what a character
feels. That's one slice of what Grace needs; attunement *in generation*
(what the blind preference test measures) is the other slice. Neither
replaces the other.
