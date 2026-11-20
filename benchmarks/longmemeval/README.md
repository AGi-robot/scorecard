# LongMemEval

[LongMemEval](https://github.com/xiaowu0162/LongMemEval) (ICLR 2025) evaluates
long-term conversational memory with 500 questions covering information
extraction, multi-session reasoning, knowledge updates, temporal reasoning,
and abstention. The data is hosted by the authors on
[Hugging Face](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned).
The dataset files are ignored by Git. The runner downloads either supported
dataset into the requested input path the first time it is needed.

The S split is about 265 MiB and the oracle split about 15 MiB. Both come from
the authors' [Hugging Face dataset](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned).

## Full-history baseline

`full_history_run.py` uses the benchmark's full-session prompt shape and writes
the official `question_id` / `hypothesis` JSONL format. It is a **long-context
baseline**, not a test of Grace's persistent memory database. Use the official
retrieval track or a dedicated memory adapter to measure a memory system.

Run the baseline with the S split; it downloads the file if it is missing:

```bash
python benchmarks/longmemeval/full_history_run.py \
  --input data/longmemeval_s_cleaned.json \
  --output results/longmemeval/ministral3-14b.jsonl \
  --base-url http://127.0.0.1:8080/v1 \
  --model ministral-3-14b-instruct-2512 \
  --limit 10
```

Omit `--limit` for all 500 questions. Runs resume by `question_id`; use
`--overwrite` to start again. The full-history split can require around 115k
tokens of context, so check the model server's context limit before starting.

For the benchmark's official QA accuracy metrics, clone the authors' repo and
follow its [`evaluate_qa.py` instructions](https://github.com/xiaowu0162/LongMemEval#testing-your-system).
The official evaluator uses an LLM judge; its selected judge model and endpoint
are part of the protocol and should be recorded with the result.

Do not compare this full-history baseline with a persistent-memory run as if
they used the same input condition. Record the mode, model, prompt protocol,
context limit, judge, and dataset revision alongside every score.
