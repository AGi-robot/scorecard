# AGi Scorecard

Shared model and agent benchmark suites for AGi projects. Start with the
[benchmark index](benchmarks/README.md) to choose a suite, see its scope, and
open its run guide. Each suite README is the source of truth for setup,
arguments, outputs, protocol, and scoring.

## Benchmark suites

### Model and capability baselines

- [BFCL](benchmarks/bfcl/README.md): V3 function calling and V4 memory/web-search tracks, plus AIVA's recent-window memory adapter.
- [Companion safety](benchmarks/companion_safety/README.md): INTIMA and AICompanionBench readiness and artifact requirements.
- [EQ-Bench and Creative Writing](benchmarks/eqbench/README.md): pinned v4 and v3 protocols; historical v2 results remain labeled separately.
- [EvalPlus](benchmarks/evalplus/README.md): HumanEval+ and MBPP+ code-generation correctness.
- [Grace Canvas Eval](benchmarks/grace_canvas_eval/README.md): canvas tool tasks.
- [Grace Chatbot Eval](benchmarks/grace_chatbot_eval/README.md): blind pairwise conversation preference.
- [IFEval](benchmarks/ifeval/README.md): strict and loose instruction following.
- [IFBench](benchmarks/ifbench/README.md): single-turn and fixed-history multi-turn instruction following.
- [LiveCodeBench](benchmarks/livecodebench/README.md): pinned release_v6 code-generation baseline.
- [LongMemEval](benchmarks/longmemeval/README.md): full-history memory baseline; does not measure persistent-memory retrieval.

See the [agent and self-coding roadmap](benchmarks/README.md#agent-and-self-coding-roadmap) for capability-based recommendations and deferred evaluations.

## Run and compare

Most model runners use an OpenAI-compatible endpoint such as
`http://127.0.0.1:8080/v1`. Check each suite's README for its exact command and
required flags; older runners use positional endpoint/model/label arguments,
while newer runners use named options. Do not assume their arguments are
interchangeable. Keep each run's raw files in that suite's `results/` directory.
Use a distinct label or output directory whenever the model, endpoint, prompt, or
benchmark protocol changes.

Prepare a smoke run with the suite's subset option before a full run. Smoke scores
are diagnostic and should not be reported as full benchmark results. Record the
model/server revision and benchmark/dataset/evaluator revisions with results;
follow the suite guide for any execution-isolation requirements.

Regenerate the combined report from the repository root with:

```bash
python benchmarks/scorecard_all.py
python benchmarks/scorecard_all.py --markdown
```

The scorecard includes completed full-run results supported by its aggregator.
Some suites have separate official evaluation commands or judge stages; their
guides explain how to produce the final score.

## Repository layout

`benchmarks/README.md` indexes all suites, shared tooling, and the agentic roadmap.
Implemented benchmark folders include a suite guide and runner/scorer as
appropriate. Shared integrations use `baseline_common.py`; cross-suite checks
live in `benchmarks/tests/`. Dependency pins and protocol validation artifacts
are documented in the index. Large datasets, generated responses, caches, and
result artifacts stay out of source control.
