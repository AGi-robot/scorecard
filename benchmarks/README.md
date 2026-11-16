# Benchmark index

Choose benchmarks that exercise a feature Grace actually has. Keep benchmark
scores separate when their input conditions or evaluators differ.

- [BFCL V3/V4](bfcl/README.md): single-turn function calling, memory, and web-search categories,
  plus a separate adapter that measures AIVA's real recent-turn memory.
- [IFEval](ifeval/README.md): strict/loose instruction following.
- [EQ-Bench v4 and Creative Writing v3](eqbench/README.md): pinned official
  judged evaluations, pending fresh runs; v2 emotion-rating results are historical.
- [Grace Canvas Eval](grace_canvas_eval/README.md): canvas tool tasks.
- [Grace Chatbot Eval](grace_chatbot_eval/README.md): human conversation preference.
- [LongMemEval](longmemeval/README.md): long-term conversational memory. The
  included runner is a full-history baseline, not persistent-memory retrieval.
- [EvalPlus](evalplus/README.md): HumanEval+ and MBPP+ code-generation
  correctness using the official scorer.
- [IFBench](ifbench/README.md): single-turn and released fixed-history
  multi-turn constraint-isolation baselines, with separate official scores.
- [LiveCodeBench](livecodebench/README.md): pinned release_v6 code-generation
  baseline with official prompts, execution checks, and pass@k metrics.
- [Companion behavior benchmarks](companion_safety/README.md): INTIMA and
  AICompanionBench readiness and artifact requirements.
- [Agent and self-coding benchmarks](agentic/README.md): BFCL V4 memory/search,
  SWE-bench Verified, Terminal-Bench, and AgentHarm recommendations.
