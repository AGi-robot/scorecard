# IFBench multi-turn baseline

This is a separate integration for the official Hugging Face dataset
[allenai/IFBench_multi-turn](https://huggingface.co/datasets/allenai/IFBench_multi-turn),
revision `e1ea65c5178fbeac522a26d12b8c71a298e9846d`, configuration
`ifbench_constraints`, split `test` (1387 examples). The name is a dataset ID,
not an available GitHub repository. The `ifeval_constraints` configuration is
deliberately excluded from this IFBench baseline.

Install the [shared dependencies](../ifbench/README.md), then run from the root:

```bash
.venv/bin/python benchmarks/ifbench_multiturn/ifbench_multiturn_run.py \
  --stage prepare --output benchmarks/ifbench_multiturn/results/preflight

export OPENAI_API_KEY=EMPTY
.venv/bin/python benchmarks/ifbench_multiturn/ifbench_multiturn_run.py \
  --base-url http://127.0.0.1:8080/v1 --model MODEL \
  --output benchmarks/ifbench_multiturn/results/MODEL
```

Protocol: submit the released `messages` exactly: user task, **fixed released
assistant response**, user rewrite constraint. Generate only the final assistant
turn. This measures constraint isolation in the released two-turn context;
it does not generate a new first-turn answer, concatenate the turns into one
user prompt, or test persistent memory. The flattened dataset `prompt` remains
the key used by the official verifier, never the generation input.

Scorer commit `488918665d53f867fa908a293769ec6e71e74aec`, temperature 0,
top_p 1, one sample, default 8192 output tokens. Report prompt-level loose
accuracy as primary, prompt strict and instruction strict/loose as secondary.
Null-filled parquet kwargs are normalized before the official scorer is called.
The [single-turn documentation](../ifbench/README.md) covers artifacts, resume,
token budgets, reasoning output, stages, licenses, and NLTK resources. Results
are stored and displayed separately; subset smoke runs never enter the scorecard.

Validation here: all 1387 pinned inputs prepared and released message schema
inspected. Synthetic tests validate final-turn scoring and preserved history.
**No model score recorded** because no model endpoint was available.
