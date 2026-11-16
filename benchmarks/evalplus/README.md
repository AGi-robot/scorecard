# EvalPlus

[EvalPlus](https://github.com/evalplus/evalplus) evaluates code-generation
correctness on HumanEval+ and MBPP+ with expanded test inputs and the official
EvalPlus scorer. It complements SWE-bench: EvalPlus measures isolated function
synthesis, while SWE-bench measures repository-level issue repair.

EvalPlus is Apache-2.0. This scorecard does not vendor its datasets, model
outputs, scorer, or code-execution environment. Install the official package
and use its commands and dataset version:

```bash
python -m pip install --upgrade evalplus
```

## Generate code from Grace's local model endpoint

Start the OpenAI-compatible model server, then run from the scorecard root.
EvalPlus sends the prompt-only code-generation task to the model; it does not
use Grace's chat persona, tools, or memory.

```bash
export OPENAI_API_KEY=EMPTY
evalplus.codegen \
  --model ministral-3-14b-instruct-2512 \
  --dataset humaneval \
  --backend openai \
  --base-url http://127.0.0.1:8080/v1 \
  --greedy \
  --root benchmarks/evalplus/results
```

Run MBPP+ separately by changing `--dataset humaneval` to `--dataset mbpp`.
Greedy decoding produces one completion per task. EvalPlus resumes generation
from existing sample files; use a new result root when changing the model,
endpoint, or decoding settings.

## Evaluate in the official sandbox

EvalPlus recommends running generated code in Docker. Pin the EvalPlus release
and matching container image for recorded comparisons. The following example
uses the official image name; replace `latest` with the pinned tag or digest
for a reproducible run:

```bash
docker run --rm \
  -v "$PWD/benchmarks/evalplus/results:/app/results" \
  ganler/evalplus:latest \
  evalplus.evaluate \
    --dataset humaneval \
    --samples /app/results/humaneval/ministral-3-14b-instruct-2512_openai_temp_0.0.jsonl
```

Repeat with `--dataset mbpp` and the corresponding MBPP sample file. The
official evaluator reports base and plus pass rates; report both. Preserve the
model server revision, EvalPlus package and dataset version, image digest,
result file, and decoding configuration with each score. HumanEval+/MBPP+ pass
rates measure code-generation accuracy, not the ability to edit Grace's source
code or safely install tools.
