# Agent and self-coding benchmarks

Grace is expected to use tools and may eventually edit her own code and add
skills. Evaluate the agent that can actually plan, call tools, edit files, run
checks, and recover from errors; a base-model score alone does not measure that
system.

## Recommended order

| Priority | Benchmark | Why it fits Grace | What it does not measure |
|---|---|---|---|
| Now | [BFCL V4](https://gorilla.cs.berkeley.edu/leaderboard.html) `memory` and `web_search` | Extends this repository's BFCL V3 function-call coverage to multi-turn memory and search tool use. | Grace's PostgreSQL memory implementation or the quality of a real web-search provider. The benchmark uses its own simulated tools. |
| Now, once code editing is enabled | [SWE-bench Verified](https://www.swebench.com/) | Tests whether an agent can understand a real repository issue, change code, and satisfy tests. This is the closest standard benchmark here to self-coding. | Safe deployment, long-term maintainability, or whether a new skill is useful to Grace. |
| Now, once terminal tools are enabled | [Terminal-Bench](https://www.tbench.ai/) | Exercises multi-step terminal tasks, command-line tools, and recovery. This covers the execution loop around coding. | Interactive desktop control or unrestricted production access. |
| Before consequential tools | [AgentHarm](https://github.com/UKGovernmentBEIS/inspect_evals/tree/main/src/inspect_evals/agentharm) | Measures harmful behavior in tool-using agents, an important capability check before adding powerful tools. | A complete security review or a guarantee against misuse. |
| Now for memory research | [LongMemEval](https://github.com/xiaowu0162/LongMemEval) | Tests recall, temporal reasoning, updates, and abstention across conversation history. | The current runner in this repo uses full history; it does not test retrieval from Grace's persistent memory. |

Use official benchmark harnesses and datasets rather than copying them into this
repository. Record the benchmark revision, agent/model versions, tool access,
configuration, and evaluator version with each result. Do not combine scores
from different harness versions into one ranking.

## Self-coding evaluation boundary

Run code-editing benchmarks in disposable, isolated task environments. Keep
benchmark task execution separate from Grace's working checkout and credentials.
A passing SWE-bench or Terminal-Bench task demonstrates performance on that
task set; it does not authorize the agent to merge changes, install skills, or
modify its running system. Track those outcomes separately in a supervised
self-improvement evaluation: proposed change, tests/checks, human acceptance,
regressions, and rollback result.

SWE-bench Verified is resource intensive: upstream evaluation uses Docker and
requires substantial disk, CPU, and memory. Start with a small smoke run before
attempting the full set. Terminal-Bench runner and task versions are evolving;
pin the upstream harness and task revision in published results.

## Add when the feature exists

- [OSWorld](https://os-world.github.io/) when Grace can control a desktop GUI.
- [τ-bench 2.0](https://github.com/sierra-research/tau2-bench) if Grace is
  evaluated on its customer-service and domain-specific tool workflows.
- [EvalPlus](https://github.com/evalplus/evalplus) for isolated code-generation
  correctness; it complements repository repair and does not test an agent's
  ability to navigate a codebase.

## Other candidates to screen before adopting

These are candidates, not part of the current scorecard run. Confirm the current
benchmark version, license, evaluator, runtime cost, and whether it can call
Grace's agent before adding an integration. A public leaderboard or a dataset
alone is not an end-to-end evaluation.

- [XBench](https://xbench.org/): consider if its current task tracks cover
  workflows Grace will perform; select a named track rather than reporting one
  undifferentiated index.
- [SEALQA](https://huggingface.co/datasets/vtllms/sealqa): screen as an
  additional QA/memory dataset after LongMemEval; check the dataset card for its
  task definition and evaluator before comparing scores.
- [PinchBench](https://pinchbench.com/), [WorkBuddy-Bench](https://github.com/Tencent/workbuddy-bench),
  [Claw-Bench](https://github.com/claw-bench/claw-bench), and
  [QwenClawBench](https://huggingface.co/datasets/skylenage-ai/QwenClawBench):
  agent or assistant benchmarks to inspect for overlap with Grace's tools and
  data-entry workflows. Prefer portable task protocols over scores tied to a
  specific agent framework.
- [MemoryBench](https://github.com/): add only after identifying the intended
  benchmark and its canonical source; the name is used by multiple projects.
  LongMemEval is the clear first public memory benchmark in this plan.
- OSWorld is the desktop-control choice when GUI computer use is implemented.
  Until then it would measure a capability Grace does not have.
- DeepSWE and ProgramBench may complement SWE-bench if Grace's coding agent is
  ready for their particular task format. Start with SWE-bench Verified for
  repository repair and Terminal-Bench for command-line execution.
- JobBench and AutomationBench-AA are worth screening when Grace's target
  workflow is clearly defined (for example, data entry). Avoid adding them just
  because they promise broad automation coverage.
- The Personal Superintelligence Index, GDPval, and Artificial Analysis Index
  are broad comparisons or indexes rather than the first task-level tests to
  wire into this scorecard. Use their published results as context, and choose
  reproducible task suites to diagnose Grace's specific strengths and failures.

For the personal-assistant direction, [τ-bench 2.0](https://github.com/sierra-research/tau2-bench)
can be screened alongside these candidates if its current domains match Grace's
real tool workflows. It is not required for the first self-coding evaluation.

## Baseline before Grace's harness

You do not need Grace's custom harness to get a first comparison. Use the
benchmark's own runner with a documented baseline agent or a direct model
adapter, then run the same tasks with Grace's agent when it is ready. Keep the
model, prompts, tool descriptions, task split, inference settings, and evaluator
fixed where the benchmark permits. Label the two systems clearly; a base model
with no tools and a tool-using agent are different conditions.

This still uses the benchmark's runner, simulator, and scorer. For example,
SWE-bench needs isolated repository tasks and tests; Terminal-Bench needs a
terminal task environment; OSWorld needs its desktop VM; and judge-based suites
need the specified evaluator. “No Grace harness” is achievable; “no harness or
evaluation code at all” is not a reproducible benchmark run. Preserve raw
predictions and per-task outcomes so a later Grace run can be scored on the same
revision and subset.

## Future evaluation roadmap

These are candidates to investigate, not installed integrations or claims of
compatibility. Before adopting one, confirm its canonical repository, license,
maintained task release, required tools, and evaluator/judge configuration.
Keep model-only baselines and complete Grace agent runs labeled separately.

| Capability or decision | Candidates | Adoption condition |
|---|---|---|
| Agent plumbing and domain workflows | τ-bench 2.0 | Defer until Grace has a working tool loop and a relevant domain. A mock domain can check plumbing if supported by the pinned release; it is not a product capability score. |
| External canvas comparison | CANVAS | Optional adapter after identifying the intended official benchmark and mapping its actions/scoring to Grace. Keep the existing custom Canvas Eval. |
| Real companion memory and persona | RealCompanion | Verify dataset provenance, license, privacy terms, task definition, and scorer before use. |
| Grace's actual goals | Goal-replay set | Curate representative goals with expected outcomes, clarification needs, and approval boundaries; establish human-reviewed rubrics. |
| Search and browsing | GAIA, BrowseComp, XBench, SEAL-0 | Search/browser tools available; verify each intended benchmark and task set. |
| Personal task execution | AutomationBench-AA, VitaBench, ClawBench | Relevant tool executor/browser available and portable tasks confirmed. |
| Shell and repository editing | SWE-bench Verified, Terminal-Bench | Disposable execution environment and functioning edit/test loop. |
| Self-coding and improvement | DeepSWE, ProgramBench, WorkBuddy Bench, MLE-Bench Lite | Confirm these names identify usable evaluation suites; audit tasks and match them to Grace's capabilities. |
| Memory implementation | MemoryBench | Identify the intended canonical suite and test the actual retrieval/storage design. LongMemEval full-history remains a different baseline. |
| Tool safety | AgentHarm | Evaluate before granting consequential real-world tool access. |
| Desktop control | OSWorld | Working computer-use interface in a controlled environment. |
| Professional tasks | GDPval, JobBench | Inspect task access, licensing, domain fit, and judge validity first. |
| Optional agent references | PinchBench, QwenClawBench | Check runtime portability, access restrictions, dependencies, and judge costs. |
| Long-document reasoning | LongBench v2 | Optional when long documents are a regular workload. |
| Scientific work | SciCode, FrontierScience-Research | Match research fields; establish required search tools and a fixed evaluation configuration. |
| Speech and vision | FLEURS, MM-Vet | Voice-input or camera pipeline implemented, including its adapter. |
| Image editing and design | PaintBench, GDB | Identify the intended official suites and adopt only when editing/design is a core deliverable. |
| Interactive reasoning | ARC-AGI-3 | Consider when selecting a reasoning model with a compatible interaction harness. |

LiveCodeBench and EvalPlus provide different task distributions; keep the
existing EvalPlus guide as optional coverage rather than treating its results
as interchangeable. Companion benchmark names also need source verification:
INTIMA, CompanionBench, and AICompanionBench must not be assumed to evaluate
the same target or use the same judge protocol.
