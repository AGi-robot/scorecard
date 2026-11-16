# Benchmark index

Choose benchmarks that exercise a feature Grace actually has. Keep benchmark
scores separate when their input conditions or evaluators differ.

- [BFCL](bfcl/README.md): function calling; current local runner covers BFCL V3
  single-turn AST categories.
- [BFCL V4](bfcl_v4/README.md): official memory-tool and web-search categories,
  plus a separate adapter that measures AIVA's real recent-turn memory.
- [LongMemEval](longmemeval/README.md): long-term conversational memory. The
  included runner is a full-history baseline, not persistent-memory retrieval.
- [EvalPlus](evalplus/README.md): HumanEval+ and MBPP+ code-generation
  correctness using the official scorer.
- [IFBench single-turn](ifbench/README.md): pinned official precise-instruction
  prompts and strict/loose verifiers.
- [IFBench multi-turn](ifbench_multiturn/README.md): separate released fixed-history
  constraint-isolation baseline, using the `ifbench_constraints` test split.
- [LiveCodeBench](livecodebench/README.md): pinned release_v6 code-generation
  baseline with official prompts, execution checks, and pass@k metrics.
- [Companion behavior benchmarks](companion_safety/README.md): INTIMA and
  AICompanionBench readiness and artifact requirements.
- [Agent and self-coding benchmarks](agentic/README.md): BFCL V4 memory/search,
  SWE-bench Verified, Terminal-Bench, and AgentHarm recommendations.
