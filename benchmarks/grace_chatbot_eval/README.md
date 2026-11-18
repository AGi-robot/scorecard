# Grace Chatbot Eval

This custom AGi evaluation uses blind pairwise human comparisons inspired by
Chatbot Arena: the same multi-turn conversations are played against two or
more models, and a rater compares the transcripts without seeing model names.
Standings come from win rates plus Elo.

The prompts and rubric are specific to Grace and have not been validated as a
standard benchmark. Pairwise human preference is an established evaluation
method, but this small, single-rater test is a subjective product-fit signal.
Use it alongside capability evaluations such as BFCL, HumanEval+, and Grace
Canvas Eval.

## The three phases

```bash
# 1. Generate: play every script against every contestant.
# Needs the model servers up. Identities are sealed in the batch file;
# raters only ever see anonymous A/B pairs.
python preference_bench.py generate \
    --contestant ministral=http://127.0.0.1:8080/v1/ministral-3-14b-instruct-2512 \
    --contestant saluki=http://127.0.0.1:8092/v1/saluki \
    --contestant swift1.5-qwen3.8-27B=http://127.0.0.1:8091/v1/swift

# 2. Rate: side-by-side blind comparison in the terminal.
python preference_bench.py rate

# 3. Score: win rates per dimension + Elo standings.
python preference_bench.py score
```

## What's tested

The system prompt is Grace's `AIVA/soma/persona/SOUL.md` plus the current
timestamp -- the same context `aiva_chat/node.py` builds -- so this tests the
deployment, not the bare model. (`--bare` drops the persona for a pure model
comparison. `--think-off` disables thinking on Qwen models for protocol
parity with Ministral, which has no thinking mode.)

The endpoint may still expose its API model ID as `swift`; the contestant label
above identifies the exact Swift 1.5 Qwen 3.8 27B build.

Six scripts, 21 user turns total:

| Script | Probes | Turns |
|---|---|---|
| `casual-evening` | warmth, small talk, noticing the hour | 4 |
| `topic-change` | coherence across abrupt topic hops, no bleed | 4 |
| `disagreement` | corrects the user kindly, holds an opinion, no sycophancy | 3 |
| `callback` | working memory inside one conversation | 4 |
| `memory-honesty` | abstains when it doesn't know, never invents | 3 |
| `emotional-support` | attunement without therapizing or platitudes | 3 |

Each turn can carry an `expect` note -- what the rater should look for --
which is shown during rating but never sent to the model.

## Rating dimensions

For every A/B pair the rater scores `warmth`, `coherence`, `persona`
(still sounds like Grace), and `overall`. Answers are `a` / `b` / `t`
(tie) / `s` (skip). Order is randomized per pair, votes append to
`results/batch_<hash>_votes.jsonl`, and `--rate` resumes where it stopped.

## Scoring

Elo (K=32, start 1500) updates on the `overall` dimension only; the printed
table shows per-dimension win rates alongside Elo so you can see *where* a
model wins, not just that it does.

## Notes

- Rating all pairs for 3 contestants x 6 scripts = 18 comparisons, each a
  few minutes. Add raters by sharing the batch file; votes append cleanly.
- Temperature defaults to 0.7 (conversational, like production). Capability
  benchmarks use 0.0; don't compare those numbers with these votes.
- The `expect` notes encode Grace's house rules (SOUL.md): emoji-prefixed
  replies, 1-2 sentences, disagree when appropriate, never invent memories.
