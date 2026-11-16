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
| Grace Canvas Eval | `canvas_draw` tool-call validity and drawing quality | 8 tasks | production DRAW_INSTRUCTIONS, temp 0.0 | scene-graph checks, no judge |
| BFCL (planned) | Tool calling on Aiko's real tool schemas | — | — | yes |

**Thinking mode.** All EQ-Bench and IFEval numbers are taken with thinking
**off**, so every model is scored under one protocol. `ministral3-14b` has no
thinking mode, so it is unaffected either way.

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
| ministral3-14b | 171 | 54.8 | 171/171 |
| minicpm5-2b | 171 | 40.4 | 171/171 |

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

**Nobody has tool-calling numbers.** Canvas eval has no scores recorded (only
renders), and BFCL has not been built. For a model whose day job is emitting
valid `canvas_draw` JSON and calling weather/moon/aurora tools, this is the
largest hole in the scorecard.

---

## In flight

| Run | State |
|---|---|
| `swift` EQ-Bench | running, ~80/171, upstream API capped at 5 prompts/min |
| `swift` IFEval | queued to auto-start when EQ-Bench releases the quota (64/541 already on disk) |

Both Swift runs are throttled by the upstream API's 5-prompts-per-minute
limit, so they take roughly 35 and 110 minutes respectively. Neither consumes
local GPU.

## Gaps

1. **Tool calling** — BFCL on Aiko's real tool schemas is not built yet.
2. **Canvas eval has no scores** — the harness works but `--out` was never
   used, so only PNG renders exist.
3. **Single-model coverage** — only Ministral and Swift have EQ-Bench and
   persona numbers. The three small models have IFEval only.
4. **No multi-turn instruction retention** — `allenai/IFBench_multi-turn` is
   available and judge-free, and would cover conversation, which is Grace's
   only interface.
5. **No long-context measurement in Grace's real context shape** — standard
   long-context benches use clean filler; Grace receives assembled episodic
   memory with distractors.
6. **Embeddings untested** — `voyage-4-nano` needs a retrieval benchmark, not
   a chat benchmark.

