# AIVA Chatbot Eval

This custom AGi evaluation uses blind pairwise human comparisons inspired by
Chatbot Arena: the same multi-turn conversations are played against two or
more models, and a rater compares the transcripts without seeing model names.
Standings come from win rates plus Elo.

The prompts and rubric are specific to AIVA and have not been validated as a
standard benchmark. Pairwise human preference is an established evaluation
method, but this small, single-rater test is a subjective product-fit signal.
Use it alongside capability evaluations such as BFCL, HumanEval+, and AIVA
Canvas Eval.

## The three phases

```bash
# 1. Generate: play every script against every contestant.
# Needs the model servers up. Identities are sealed in the batch file;
# raters only ever see anonymous A/B pairs.
python preference_bench.py generate \
    --contestant ministral=http://127.0.0.1:8080/v1/ministral-3-8b-instruct-2512-abliterated \
    --contestant saluki=http://127.0.0.1:8092/v1/saluki \
    --contestant swift1.5-qwen3.8-27B=http://127.0.0.1:8091/v1/swift

# 2. Rate: side-by-side blind comparison in the terminal.
python preference_bench.py rate

# 3. Score: win rates per dimension + Elo standings.
python preference_bench.py score
```

Generation calls each model's OpenAI-compatible endpoint directly. It does not
start or import AIVA's runtime. By default, the harness sends the bundled
`prompts/SOUL.md` snapshot, the run timestamp, and each script's
conversation history. The batch records both the persona hash and the hash of
the exact system prompt sent. This keeps the evaluation stable when AIVA's
live prompt or runtime changes. A deliberate persona revision should be saved
as a new snapshot and passed with `--system-prompt-file`.

For bare model comparisons, add `--bare-model` to the `generate` command. This
omits the persona and timestamp; the scripted conversation history remains.
The two modes are recorded separately in each batch.

## What's tested

The default AIVA-prompt mode tests the persona prompt and conversation-history
handling around each endpoint. It does not test AIVA's running chat service,
memory database, tools, or router. `--bare-model` compares the model endpoints
without the persona. `--think-off` disables thinking on Qwen models for protocol
parity with Ministral, which has no thinking mode. Keep the setting fixed across
contestants and record the serving-model revision and quantization with each run.

## Prompt variants (anti-memorization)

The six scripts are fixed by default -- the standard Arena setup, identical
prompts for every contestant, blinded and shuffled at rate time. A single
rater judging all 18 comparisons will inevitably start recognizing the
conversations. `generate --variant` counters that without changing what is
measured (same turn count, same probes, same rater notes):

- `--variant a` (default): original scripts, full standard comparability.
- `--variant b`: alternate user wordings for all six scripts.
- `--variant alternate` (+ `--variant-seed`, default 7): each contestant play
  randomly gets the a or b wording; the choice is recorded per transcript in
  the batch, so any run stays auditable. Rate and score need no changes.

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
(still sounds like AIVA), and `overall`. Answers are `a` / `b` / `t`
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
- The `expect` notes encode AIVA's house rules (SOUL.md): emoji-prefixed
  replies, 1-2 sentences, disagree when appropriate, never invent memories.
