#!/usr/bin/env python3
"""Pinned LiveCodeBench release_v6 code-generation baseline."""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from baseline_common import HERE, checkout, digest, download, initialize, parser, responses, write_json

REVISION = "28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24"
DATA_REVISION = "0fe84c3912ea0c4d4a78037083943e8f0c4dd505"


def index_files(paths):
    tasks = []
    for path in paths:
        with path.open("rb") as source:
            while True:
                offset = source.tell()
                line = source.readline()
                if not line:
                    break
                if line.strip():
                    row = json.loads(line)
                    tasks.append({"id": str(row["question_id"]), "path": path, "offset": offset})
    return sorted(tasks, key=lambda t: t["id"])


def load_row(task):
    with task["path"].open("rb") as source:
        source.seek(task["offset"])
        return json.loads(source.readline())


def main():
    p = parser("LiveCodeBench code_generation_lite release_v6", default_n=10, temperature=0.2, max_tokens=2000)
    p.add_argument("--num-process-evaluate", type=int, default=1)
    p.add_argument("--timeout", type=int, default=6)
    args = p.parse_args()
    if args.n != 10 or args.temperature != 0.2:
        raise ValueError("This baseline fixes n=10 and temperature=0.2")
    if args.timeout < 1 or args.num_process_evaluate < 1:
        raise ValueError("Evaluation timeout and process count must be positive")
    official = checkout("https://github.com/livecodebench/livecodebench.git", REVISION,
                        args.official or HERE / ".cache" / "LiveCodeBench")
    files = ["test.jsonl"] + [f"test{i}.jsonl" for i in range(2, 7)]
    paths = [download(f"https://huggingface.co/datasets/livecodebench/code_generation_lite/resolve/{DATA_REVISION}/{name}",
                      HERE / ".cache" / DATA_REVISION / name) for name in files]
    # Match ALLOWED_FILES['release_v6'] in the official pinned dataset script.
    path = HERE / ".cache" / DATA_REVISION / "release_v6-index.json"
    write_json(path, {p.name: digest(p) for p in paths})
    tasks = index_files(paths)
    total = len(tasks)
    tasks = tasks[:args.limit] if args.limit else tasks
    if not tasks or len({t['id'] for t in tasks}) != len(tasks):
        raise ValueError("Empty dataset or duplicate question IDs")
    protocol = {"suite": "LiveCodeBench release_v6", "official_revision": REVISION,
                "dataset": "livecodebench/code_generation_lite", "dataset_revision": DATA_REVISION,
                "release": "release_v6", "files": files, "scenario": "codegeneration",
                "prompt_style": "OpenAIChat", "n": 10, "temperature": 0.2, "top_p": 0.95,
                "timeout": args.timeout, "num_process_evaluate": args.num_process_evaluate,
                "date_filter": None, "primary_metric": "pass@1"}
    initialize(args, protocol, path, total)
    if args.stage == "prepare":
        print(f"Prepared {len(tasks)}/{total} tasks: LiveCodeBench release_v6")
        return
    sys.path.insert(0, str(official))
    # Upstream prompt imports open few-shot files relative to the repository root.
    os.chdir(official)
    from lcb_runner.benchmarks.code_generation import CodeGenerationProblem
    from lcb_runner.lm_styles import LMStyle
    from lcb_runner.prompts.code_generation import format_prompt_generation
    from lcb_runner.utils.extraction_utils import extract_code
    def messages(task):
        row = load_row(task)
        # Official formatting needs only these two fields; avoid decoding private tests during generation.
        question = SimpleNamespace(question_content=row["question_content"], starter_code=row["starter_code"])
        return format_prompt_generation(question, LMStyle.OpenAIChat)

    outputs = responses(args, tasks, messages, top_p=0.95)
    if outputs is None:
        return
    codes = [[extract_code(text, LMStyle.OpenAIChat) for text in samples] for samples in outputs]
    write_json(args.output / "custom_outputs.json", [{"question_id": t["id"], "code_list": c} for t, c in zip(tasks, codes)])
    from lcb_runner.evaluation import codegen_metrics
    from lcb_runner.evaluation.pass_k_utils import compute_metrics_from_results
    raw, metadata = {}, []
    # Score one problem at a time to bound private-test memory, then use the
    # official estimator across all per-sample test outcomes.
    for index, (task, samples) in enumerate(zip(tasks, codes)):
        problem = CodeGenerationProblem(**load_row(task))
        part = codegen_metrics([problem.get_evaluation_sample()], [samples],
                               k_list=[1, 5, 10], num_process_evaluate=args.num_process_evaluate,
                               timeout=args.timeout)
        raw[index] = part[1][0]
        metadata.append(part[2][0])
    metrics = [compute_metrics_from_results(raw, k_list=[1, 5, 10]), raw, metadata]
    write_json(args.output / "official_metrics.json", metrics)
    result = {"suite": protocol["suite"], "model": args.model, "n": len(tasks),
              "full_run": len(tasks) == total, "protocol": protocol,
              **{k: float(v) for k, v in metrics[0].items() if k.startswith("pass@")}}
    write_json(args.output / "summary.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
