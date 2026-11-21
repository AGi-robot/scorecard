# Benchmark index

Choose benchmarks that exercise capabilities Grace has or is preparing to add. Keep scores separate when prompts, tools, datasets, or evaluators differ. Each suite guide is the source of truth for commands, arguments, outputs, and scoring.

## Implemented benchmark suites

- [BFCL](bfcl/README.md): official BFCL V4 across single-turn, multi-turn, live, agentic, and format-sensitivity tracks; Mind's conversation-window adapter is separate.
- [Companion safety](companion_safety/README.md): INTIMA and AICompanionBench readiness, protocols, and artifact requirements.
- [EQ-Bench and Creative Writing](eqbench/README.md): pinned EQ-Bench v4 and Creative Writing v3 plans; historical EQ-Bench v2 results remain separately labeled.
- [EvalPlus](evalplus/README.md): HumanEval+ and MBPP+ code-generation correctness.
- [Grace Canvas Eval](grace_canvas_eval/README.md): Grace's canvas tool tasks.
- [Grace Chatbot Eval](grace_chatbot_eval/README.md): blind pairwise conversation preference.
- [IFEval](ifeval/README.md): strict and loose instruction following.
- [IFBench](ifbench/README.md): single-turn and fixed-history multi-turn instruction following, reported separately.
- [LiveCodeBench](livecodebench/README.md): pinned release_v6 code-generation baseline and official pass@k scoring.
- [LongMemEval](longmemeval/README.md): full-history conversational-memory baseline; this does not test persistent-memory retrieval.

## Shared benchmark tooling

`baseline_common.py` provides shared request, generation, resume, and validation helpers for the pinned IFBench and LiveCodeBench integrations. `ifbench_baseline.py` is the consolidated IFBench command-line entry point. `baseline-requirements.lock` pins their dependencies, and `baseline-validation.json` records the validated protocol and data revisions. `scorecard_all.py` aggregates supported completed runs; it does not replace suite-specific official scoring. `tests/` contains cross-suite regression tests. `REVIEW.md` records repository review findings and compatibility notes.

## Agent and self-coding roadmap

Grace is expected to use tools and may eventually edit her own code and add skills. Evaluate the agent that can plan, call tools, edit files, run checks, and recover from errors; a base-model score alone does not measure that system.

| Priority | Benchmark | Fit and limits |
|---|---|---|
| Next | [BFCL V4](https://gorilla.cs.berkeley.edu/leaderboard.html) memory and web search | Extends function-call testing with benchmark-simulated memory/search tools, not Grace's PostgreSQL implementation or real search provider. |
| When code editing is enabled | [SWE-bench Verified](https://www.swebench.com/) | Repository issue resolution; does not measure safe deployment or long-term maintainability. |
| When terminal tools are enabled | [Terminal-Bench](https://www.tbench.ai/) | Multi-step command-line tasks and recovery; does not measure desktop use. |
| Before consequential tools | [AgentHarm](https://github.com/UKGovernmentBEIS/inspect_evals/tree/main/src/inspect_evals/agentharm) | Harmful behavior in tool-using agents; not a complete security review. |
| Memory research | [LongMemEval](https://github.com/xiaowu0162/LongMemEval) | Recall, temporal reasoning, updates, and abstention; distinguish retrieval from this repo's full-history baseline. |

Run code-editing benchmarks in disposable environments separated from Grace's checkout and credentials. A passing task does not authorize merging, installing skills, or changing Grace's running system. Record task, harness, model, tool, configuration, and evaluator revisions. SWE-bench needs Docker and substantial resources; start with a smoke run. Pin Terminal-Bench tasks and harness.

### Future candidates

| Capability or decision | Candidates | Adoption condition |
|---|---|---|
| Tool plumbing and domain workflows | [τ-bench 2.0](https://github.com/sierra-research/tau2-bench) | Working tool loop and relevant domain; mock runs are plumbing checks only. |
| Canvas comparison | CANVAS | Identify the official suite and map its actions/scoring; retain the custom Canvas Eval. |
| Companion memory/persona | RealCompanion | Verify data provenance, license, privacy terms, task, and scorer. |
| Grace's own goals | Goal-replay set | Curate goals, expected outcomes, clarification needs, approval boundaries, and reviewed rubrics. |
| Search and browsing | GAIA, BrowseComp, XBench, SEAL-0 | Search/browser tools available; identify and pin the specific task releases. |
| Personal task execution | AutomationBench-AA, VitaBench, ClawBench | Relevant executor/browser available and tasks portable. |
| Self-coding and improvement | DeepSWE, ProgramBench, WorkBuddy Bench, MLE-Bench Lite | Verify each suite's identity and fit to Grace's actual capabilities. |
| Memory | MemoryBench | Identify the canonical suite and test the actual storage/retrieval design. |
| Desktop control | OSWorld | Working computer-use interface in a controlled environment. |
| Professional work | GDPval, JobBench | Check task access, license, domain fit, and evaluator validity. |
| Optional agent references | PinchBench, QwenClawBench | Check portability, access restrictions, dependencies, and judge costs. |
| Long documents | LongBench v2 | Optional if long documents are a regular workload. |
| Science | SciCode, FrontierScience-Research | Match Grace's fields and establish tools and fixed evaluation settings. |
| Speech and vision | FLEURS, MM-Vet | Voice or camera pipeline and adapter implemented. |
| Image editing and design | PaintBench, GDB | Identify official suites; adopt when editing/design is a core deliverable. |
| Interactive reasoning | ARC-AGI-3 | Consider when selecting a model with a compatible interaction harness. |

Screen SEALQA, PinchBench, WorkBuddy-Bench, Claw-Bench, QwenClawBench, DeepSWE, ProgramBench, JobBench, AutomationBench-AA, and broad indexes for source, license, task fit, and evaluator before integration. INTIMA, CompanionBench, and AICompanionBench may measure different systems and judge protocols. EvalPlus complements repository repair with code-generation correctness; its scores are not interchangeable with LiveCodeBench. Keep model-only and full Grace-agent results labeled separately.
