# Companion behavior benchmarks

These benchmarks are selected for evaluating AIVA's companion behavior,
relationship boundaries, and safety. Keep their scores separate from general
chat preference, memory retrieval, and tool-use scores.

| Benchmark | Planned use | Readiness |
|---|---|---|
| [INTIMA](https://huggingface.co/papers/2508.09998) | Probe companionship boundaries across the reported 368 prompts and 31 behaviors. | Paper reference is known; a canonical downloadable prompt set, evaluator, and license still need confirmation before a reproducible runner can be added. |
| [AICompanionBench](https://arxiv.org/abs/2606.04867) | Evaluate harmful or manipulative behavior across companion conversations, including implicit cases and benign false positives. | Paper reference is known; the task data, exact judge prompt/model, evaluator code, and usage terms still need confirmation. |

The scorecard intentionally does not reproduce benchmark prompts from paper
summaries or substitute a locally written LLM judge. Once the authors' official
task data and evaluation artifacts are available, add a runner that pins their
revisions and records the judge configuration. Until then, treat these as
research priorities rather than completed benchmark integrations.

These suites include sensitive material such as self-harm, sexual behavior,
aggression, and manipulation. Any eventual run should be an offline evaluation
with controlled data handling, not prompts sent through AIVA's live WebUI.
