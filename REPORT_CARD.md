# AGi Scorecard

Model benchmark results for the Grace project. Each section identifies its
scorer and protocol; custom harness checks and partial historical runs are
labeled separately from official benchmark scores.

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

| Label | Model / build | Size | Intended role |
|---|---|---:|---|
| `ministral3-14b` | Ministral 3 14B Instruct 2512 UD-Q4KXL | 14B | Front-end chatbot for conversation and persona |
| `swift1.5-qwen3.8-27B` | Swift 1.5 Qwen 3.8 27B GSQ-RCO IQ3_S MTP | 27B | Back-end agent for reasoning, tool calling, and vision |
| `minicpm5-2b` | MiniCPM 5 | 2B | Cheap helper or robot-side model |
| `agents-a1-4b` | Agents A1 | 4B | Cheap helper or robot-side model |
| `neohorse-1-4b` | NeoHorse | 4B | Cheap helper or robot-side model |

In this planned split, visual inputs can be routed to `swift1.5-qwen3.8-27B`, so Ministral vision
is not needed unless the front-end must process images directly. Scores for the
two component models do not predict the routed Grace system; evaluate that
system end to end when it is available.

## Benchmarks and protocol

| Benchmark | What it measures | n | Protocol | Official scorer |
|---|---|---:|---|---|
| [BFCL V4](benchmarks/bfcl/README.md) | Full function calling and agentic tool use: single-turn, multi-turn, live, memory/search, hallucination, and format sensitivity | category-specific | Pinned official V4 harness; complete protocol required for overall score | yes (official BFCL evaluator) |
| [EQ-Bench v2 (historical)](benchmarks/eqbench/README.md) | Emotion recognition — rating 4 emotions per scenario | 171 | temp 0.01, max_tokens 60, up to 3 parse attempts | yes (official full-scale) |
| [EQ-Bench v4 / Creative Writing v3](benchmarks/eqbench/README.md) | Applied emotional/social intelligence / judged writing quality | 120 personas / 32 prompts × 3 | Pinned official protocols and judges; v4 uses 16-message conversations; writing temp 0.7, min_p 0.1 | yes (official; runs pending) |
| [EvalPlus](benchmarks/evalplus/README.md) | Code-generation correctness on HumanEval+ and MBPP+ with expanded tests | dataset-specific | Greedy generation; official sandbox/scorer; pin package and image for each run | yes (official EvalPlus scorer) |
| [Grace Canvas Eval](benchmarks/grace_canvas_eval/README.md) | `canvas_draw` tool-call validity and drawing quality | 8 tasks | Production DRAW_INSTRUCTIONS, temp 0.0, max_tokens 3072 | scene-graph checks; no judge |
| [Grace Chatbot Eval](benchmarks/grace_chatbot_eval/README.md) | Persona fit: warmth, coherence, persona, overall | 6 scripts / 21 turns | SOUL.md + timestamp, temp 0.7, blind pairwise rating | human rater; Elo K=32 |
| [IFEval](benchmarks/ifeval/README.md) | Verifiable instruction/format compliance on final responses | 541 | temp 0.0, max_tokens 2048, raw prompt, no system prompt | yes (Google Research scorer, vendored) |
| [IFBench single-turn](benchmarks/ifbench/README.md) | Precise instruction following | 300 | Pinned test data, temp 0, one response, prompt-level loose accuracy primary | yes (pinned official library) |
| [IFBench multi-turn](benchmarks/ifbench/README.md) | Constraint isolation in released fixed conversation history | 1,387 | Pinned `ifbench_constraints/test`, temp 0, generate final response only | yes (pinned official library) |
| [LiveCodeBench](benchmarks/livecodebench/README.md) | Code generation with execution-based pass@k | 1,055 | Pinned cumulative release_v6 lite, n=10, temp 0.2, top_p 0.95 | yes (pinned official checker and estimator) |
| [LongMemEval](benchmarks/longmemeval/README.md) | Recall, multi-session reasoning, knowledge updates, temporal reasoning, and abstention | 500 | Full-history long-context baseline; official QA evaluator uses a configured LLM judge | yes (official evaluator; no result recorded) |

BFCL V4, EQ-Bench v4, Creative Writing v3, EvalPlus, IFBench, LiveCodeBench,
and LongMemEval have no completed model scores here. EQ-Bench v2 results and
the incomplete BFCL V3 artifacts below are historical; the V3 subset rates are
not full benchmark scores. Synthetic scorer fixtures and smoke tests are not
benchmark results. INTIMA and AICompanionBench are research-readiness entries,
not runnable integrations ([guide](benchmarks/companion_safety/README.md)).

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

### Historical BFCL V3 responses — incomplete samples

The V3 runner has been removed. These retained response files cover different
fractions of the old 1,240-task local run and are **not official full BFCL
scores**. They are kept temporarily until a complete V4 evaluation is run.

| Model | Correct responses | Coverage | Accuracy on saved subset |
|---|---:|---:|---:|
| minicpm5-2b | 826/1,071 | 86% | 77.1% |
| neohorse-1-4b | 602/745 | 60% | 80.8% |
| ministral3-14b | 664/852 | 69% | 77.9% |
| agents-a1-4b | 278/423 | 34% | 65.7% |

Coverage and category mix differ, so these subset rates should not be ranked
against one another or compared with BFCL V4 leaderboard scores.

### EQ-Bench v2 — emotion recognition

| Model | n | Score | Parseable |
|---|---:|---:|---:|
| neohorse-1-4b | 171 | **57.0** | 171/171 |
| agents-a1-4b | 171 | 56.7 | 171/171 |
| swift1.5-qwen3.8-27B | 171 | 56.8 | 171/171 |
| ministral3-14b | 171 | 54.8 | 171/171 |
| minicpm5-2b | 171 | 40.4 | 171/171 |

### Grace Canvas Eval — `canvas_draw` tool calling

Eight tasks scored from the canvas engine's own scene graph — no reference
images, no judge. `check_score` is the fraction of per-task checks passed
(object count, palette, layout rhythm, coverage, overlap, edit semantics);
`valid_rate` is the fraction of calls the validator accepted without repair.

| Run | Arm | Drew | Actions | check_score | valid_rate |
|---|---|---:|---:|---:|---:|
| swift1.5-qwen3.8-27B | think-off | 8/8 | 3691 | **0.690** | 0.500 |
| swift1.5-qwen3.8-27B | think-off, forced tool | 8/8 | 6662 | **0.690** | 0.375 |
| neohorse-1-4b | think-off | 8/8 | 73 | 0.595 | 0.750 |
| ministral3-14b | think-off | 8/8 | 36 | 0.595 | 0.375 |
| minicpm5-2b | think-on, budget-capped | 8/8 | 49 | 0.595 | 0.250 |
| agents-a1-4b | think-on, budget-capped | 8/8 | 27 | 0.595 | 0.375 |
| neohorse-1-4b | think-on, budget-capped | 8/8 | 45 | 0.571 | 0.625 |
| swift1.5-qwen3.8-27B | think-on | 5/8 | 1404 | 0.500 | 0.125 |
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
2. **One poison action voided the scene** — e.g. the `swift1.5-qwen3.8-27B` lighthouse action 11
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
| swift1.5-qwen3.8-27B | 11 | 1461 | 18% | coherence 3/3, overall 2/2, persona 4/4, warmth 2/2 |

Small n — single rater, six scripts. Treat as a directional signal only.

---

## What the numbers say

**Ministral is the most likeable and the least compliant model in the set.**
It wins the blind persona test (Elo 1539) but comes last on IFEval (65.1
strict) — behind a 2B model by 20 points. For Grace this is the central
tension: SOUL's emoji-and-colon prefix and 1–2 sentence limit are hard
constraints, and "warmest" does not mean "follows the contract".

**The smaller models show different profiles across tests.** `minicpm5-2b`
tops the completed IFEval results (85.6) but has the lowest historical EQ-Bench
v2 score (40.4). These separate model-only scores do not validate a model-role
split or the planned Ministral-front-end/`swift1.5-qwen3.8-27B`-back-end system. The smaller
models have not been evaluated as helpers in that routed system.

**Standard function calling still needs a full run.** BFCL V4 is the active
tool-calling evaluation and has not yet been run. Grace Canvas Eval is a
separate custom test: the current `swift1.5-qwen3.8-27B` think-off runs have the highest
recorded `check_score` (0.690), while prompts, reasoning modes, and action
counts vary across runs. These canvas results do not measure the combined
Ministral/`swift1.5-qwen3.8-27B` system.

**`valid_rate` and `check_score` measure different things.** A call can be
well-formed without producing a complete scene, and a strong scene score can
include repaired actions. Read both metrics together; neither alone measures
the quality of the routed agent system.

**Forcing the tool did not improve the `swift1.5-qwen3.8-27B` canvas score in this run.** The
think-off forced and unforced runs both scored 0.690, while the forced run
used 6,662 actions versus 3,691. It increased output without improving the
scene-graph score.

---

## In flight

| Run | State |
|---|---|
| `swift1.5-qwen3.8-27B` IFEval | ~174/541, upstream API capped at 5 prompts/min |
| `neohorse-1-4b` canvas think-on | last local run, ~4/8 tasks |

Both are throttled by the upstream API's 5-prompts-per-minute limit; neither
consumes local GPU.

## Gaps

1. **BFCL V4 run pending** — the active test is the official full V4
   protocol. Its memory and web-search tasks use benchmark tools/backends; they
   do not directly measure AIVA's SQLite history or its `/web` path. The
   retained V3 responses above are incomplete historical samples.
2. **Coverage differs by suite** — all five listed models have historical
   EQ-Bench v2 results; the blind persona preference results cover only
   `swift1.5-qwen3.8-27B` and `ministral3-14b`.
3. **Multi-turn scores pending** — the IFBench fixed-history multi-turn runner
   is integrated; a configured model endpoint and completed run are still needed.
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


