# Benchmark index

Choose benchmarks that exercise a feature Grace actually has. Keep benchmark
scores separate when their input conditions or evaluators differ.

- [BFCL](bfcl/README.md): function calling; current local runner covers BFCL V3
  single-turn AST categories.
- [BFCL V4](bfcl_v4/README.md): official memory and web-search categories,
  using a local SearXNG backend for search.
- [LongMemEval](longmemeval/README.md): long-term conversational memory. The
  included runner is a full-history baseline, not persistent-memory retrieval.
- [Agent and self-coding benchmarks](agentic/README.md): BFCL V4 memory/search,
  SWE-bench Verified, Terminal-Bench, and AgentHarm recommendations.
