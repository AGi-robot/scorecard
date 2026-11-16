# AGi Scorecard

Model benchmark results for the Grace project. Every number here is produced by a
harness in this repo and scored with the benchmark's own official code — no
hand-tuned numbers, no LLM judges unless the benchmark specifies one.

## Regenerating

```bash
cd scorecard/benchmarks
python3 scorecard_all.py                 # one table to stdout
python3 scorecard_all.py --markdown      # the tables in this file
```

`scorecard_all.py` reads the raw result files from each suite and normalizes
them to a 0-100 scale so benchmarks with different units can be read side by
side. Per-benchmark raw data and the exact protocol live in each suite's
`README.md`.

## Model roster

| Label | Size | Intended role |
|---|---:|---|
| `ministral3-14b` | 14B | Grace's primary brain — chat, memory, persona |
| `swift` | 27B | Pruned baseline / alternative brain — quantised reference |
| `minicpm5-2b` | 2B | Cheap helper or robot-side model |
| `agents-a1-4b` | 4B | Cheap helper or robot-side model |
| `neohorse-1-4b` | 4B | Cheap helper or robot-side model |

## Benchmarks and protocol

| Benchmark | What it measures | n | Protocol | Official scorer |
|---|---|---:|---|---|
| IFEval | Instruction/format compliance on the final response | 541 | temp 0.0, max_tokens 2048, raw prompt, no system prompt | yes (google-research, vendored) |
| EQ-Bench v2 | Emotion recognition — rating 4 emotions per scenario | 171 | temp 0.01, max_tokens 60, up to 3 attempts to parse | yes (official full-scale) |
| Grace Chatbot Eval | Persona fit — warmth, coherence, persona, overall | 6 scripts | SOUL.md + current timestamp, temp 0.7, blind pairwise | single human rater, Elo K=32 |
| Grace Canvas Eval | `canvas_draw` tool-call validity and drawing quality | 8 tasks | production DRAW_INSTRUCTIONS, temp 0.0, max_tokens 3072 | scene-graph checks, no judge |
| BFCL V3 | Single-turn function calling: simple, multiple, parallel, and irrelevance | 1,170 | temp 0.0, max_tokens 1024, think-off | yes (AST semantics ported from official checker) |
| [IFBench single-turn](benchmarks/ifbench/README.md) | Precise instruction following | 300 | pinned test data, temp 0, one response, prompt loose primary | yes (pinned official library) |
| [IFBench multi-turn](benchmarks/ifbench/README.md) | Constraint isolation in released fixed conversation history | 1,387 | pinned ifbench_constraints/test, temp 0, final response only | yes (pinned official library) |
| [LiveCodeBench](benchmarks/livecodebench/README.md) | Code generation | 1,055 | pinned cumulative release_v6 lite, n=10, temp 0.2, top_p 0.95, pass@1/pass@5 | yes (pinned official checker and estimator) |

These three baseline integrations have no model scores recorded yet: this
environment had no configured model endpoint. Synthetic scorer fixtures and
subset smoke tests are not benchmark results and never enter scorecard tables.

**Thinking mode.** All EQ-Bench and IFEval numbers are taken with thinking
**off**, so every model is scored under one protocol. `ministral3-14b` has no
thinking mode, so it is unaffected either way. Canvas is reported per arm
because the arms disagree by more than any other benchmark here.

---

## Results

### IFEval — instruction following (strict / loose)

| Model | n | Strict | Loose | Time |
|---|---:|---:|---:|---:|
| minicpm5-2b | 541 | **85.6** | **87.2** | 82 min |
| neohorse-1-4b | 541 | 79.1 | 83.0 | 113 min |
| agents-a1-4b | 541 | 76.3 | 81.2 | 117 min |
| ministral3-14b | 541 | 65.1 | 71.5 | 219 min |

### EQ-Bench v2 — emotion recognition

| Model | n | Score | Parseable |
|---|---:|---:|---:|
| neohorse-1-4b | 171 | **57.0** | 171/171 |
| agents-a1-4b | 171 | 56.7 | 171/171 |
| swift | 171 | 56.8 | 171/171 |
| ministral3-14b | 171 | 54.8 | 171/171 |
| minicpm5-2b | 171 | 40.4 | 171/171 |

### Grace Canvas Eval — `canvas_draw` tool calling

Eight tasks scored from the canvas engine's own scene graph — no reference
images, no judge. `check_score` is the fraction of per-task checks passed
(object count, palette, layout rhythm, coverage, overlap, edit semantics);
`valid_rate` is the fraction of calls the validator accepted without repair.

| Run | Arm | Drew | Actions | check_score | valid_rate |
|---|---|---:|---:|---:|---:|
| swift | think-off | 8/8 | 3691 | **0.690** | 0.500 |
| swift | think-off, forced tool | 8/8 | 6662 | **0.690** | 0.375 |
| neohorse-1-4b | think-off | 8/8 | 73 | 0.595 | 0.750 |
| ministral3-14b | think-off | 8/8 | 36 | 0.595 | 0.375 |
| minicpm5-2b | think-on, budget-capped | 8/8 | 49 | 0.595 | 0.250 |
| agents-a1-4b | think-on, budget-capped | 8/8 | 27 | 0.595 | 0.375 |
| neohorse-1-4b | think-on, budget-capped | 8/8 | 45 | 0.571 | 0.625 |
| swift | think-on | 5/8 | 1404 | 0.500 | 0.125 |
| agents-a1-4b | think-off | 8/8 | 18 | 0.405 | **1.000** |
| minicpm5-2b | think-off | 8/8 | 22 | 0.310 | 0.375 |

Scores are post-repair (see *Blank renders* below): the engine now drops
poison actions instead of voiding the scene, and tier-4 renders seed+edit.
`Drew` counts tasks with at least one emitted action; `render_rate` is 1.0
across the board after the fix, so it is omitted.

#### Blank renders — root causes, all fixed or explained

Every blank-white PNG traced to one of four causes; none required rerunning
the model:

1. **Unbounded thinking starved the tool call** — the trace consumed all
   3072 tokens, 0 actions emitted. Fixed by `--reasoning-budget 1024` on the
   serving config (think-on arms rerun under the cap).
2. **One poison action voided the scene** — e.g. Swift's lighthouse action 11
   (`x: [58, 175]`, a list where a number belongs). The old repair only
   handled three slip types; anything else failed revalidation and the
   harness fell back to an empty list. Fixed in the engine:
   `repair_model_actions` is now per-action (drop the poison, keep the
   fourteen good ones), plus coercions for list-valued coords and
   point-less lines. Valid input passes through byte-identical (self-tested).
3. **Tier-4 rendered without the seed** — the harness rendered only the edit
   actions. Fixed (seed+edit), T4 rescored to 4/4 for every model.
4. **Genuine model failures** — T5's 3205-action dump (over the 100-action
   cap) and empty think-on emissions remain blank, correctly.

### Grace Chatbot Eval — blind persona preference (Elo)

| Model | Votes | Elo | Win rate | Per-dimension wins |
|---|---:|---:|---:|---|
| ministral | 16 | **1539** | 31% | coherence 3/3, overall 5/5, persona 3/3, warmth 5/5 |
| swift | 11 | 1461 | 18% | coherence 3/3, overall 2/2, persona 4/4, warmth 2/2 |

Small n — single rater, six scripts. Treat as a directional signal only.

---

## What the numbers say

**Ministral is the most likeable and the least compliant model in the set.**
It wins the blind persona test (Elo 1539) but comes last on IFEval (65.1
strict) — behind a 2B model by 20 points. For Grace this is the central
tension: SOUL's emoji-and-colon prefix and 1–2 sentence limit are hard
constraints, and "warmest" does not mean "follows the contract".

**The 2B and the 4Bs are specialists, not generalists.** `minicpm5-2b` tops
IFEval (85.6) but is last on EQ-Bench (40.4) — strong format compliance, weak
emotional perception. The two 4Bs invert that: mid-pack on IFEval, top of the
table on EQ-Bench. A role split — 2B/4B as the robot-side or helper tier,
Ministral as the brain — is supported by the data, but the small models have
never been tested for tool calling, which is the job the helper tier would do.

**Nobody has a tool-calling story yet.** Canvas eval now covers all five
models and the picture is clear: `swift` draws a real scene (461 actions per
task, 0.667), `agents-a1-4b` emits two or three shapes per task and lands at
0.357, and `ministral3-14b` emits four and lands at 0.452 with a `valid_rate`
of 0.375 — roughly a quarter of its canvas calls would need repair in
production. For the canvas path specifically, `swift` is the clear winner and
`ministral3-14b` is the weakest on both axes.

**`valid_rate` and `check_score` measure different things.** `agents-a1-4b`
has a perfect `valid_rate` (1.000) and the second-worst `check_score`: every
call it makes is well-formed and consumable, but the scene is nearly empty. A
single amber blob satisfies "a red apple with a brown stem and one green
leaf" as far as the validator is concerned. `valid_rate` is the metric for a
helper model that must never break the tool contract; `check_score` is the
metric for a model that has to draw.

**Forcing the tool did not help.** Production sets `tool_choice` on the
canvas call; running Swift that way scored 0.452 against 0.667 unforced, with
832 actions per task instead of 461 — more verbose, no better.

---

## In flight

| Run | State |
|---|---|
| `swift` IFEval | ~174/541, upstream API capped at 5 prompts/min |
| `neohorse-1-4b` canvas think-on | last local run, ~4/8 tasks |

Both are throttled by the upstream API's 5-prompts-per-minute limit; neither
consumes local GPU.

## Gaps

1. **BFCL V4 agent loop** — BFCL V3 covers single-turn function calls; V4
   memory and web-search are documented in `benchmarks/bfcl_v4/`. The current
   AIVA history store does not implement BFCL memory tools, and its `/web`
   prefix does not call SearXNG, so those remain separate from end-to-end AIVA
   evaluation.
2. **Multi-model coverage is uneven** — only `swift`, `ministral3-14b` and
   `neohorse-1-4b` have EQ-Bench numbers, and only `swift` and `ministral3-14b`
   have persona numbers.
3. **No multi-turn instruction retention** — `allenai/IFBench_multi-turn` is
   available and judge-free, and would cover conversation, which is Grace's
   only interface.
4. **No persistent-memory retrieval measurement** — LongMemEval full-history
   is a useful baseline, but Grace needs a retrieval adapter to evaluate her
   PostgreSQL-backed memory with the same questions.
5. **Embeddings untested** — `voyage-4-nano` needs a retrieval benchmark, not
   a chat benchmark.
6. **Canvas has no image-level judge** — `check_score` verifies countable
   properties (object count, palette, rhythm, coverage), not whether the
   drawing resembles the subject. The harness supports an optional VLM judge
   (`--judge-base-url`/`--judge-model`) that would cover that axis.
7. **No standard code-generation score** — EvalPlus is documented for
   HumanEval+/MBPP+ evaluation, but no model results have been collected yet.


