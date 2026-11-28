#!/usr/bin/env python3
"""Round 1b: blind visual judge over saved baseline renders.

For each render PNG (results baseline, all labels), ask a vision-capable
judge model for a 0-10 score + one-line justification. No drawing involved.
Writes results/judge-<judge-label>.json. Skips tasks whose PNG is missing.
Resumable: existing judge file entries are kept, only missing ones are run.
"""
import argparse
import base64
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aiva_canvas_eval import judge_image  # noqa: E402

LABELS = ["ministral3-8b", "swift15-qwen3.8-27b-local", "saluki-27b",
          "minicpm5-2b", "neohorse-1-4b", "agents-a1-4b"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge-base-url", required=True)
    ap.add_argument("--judge-model", required=True)
    ap.add_argument("--judge-label", required=True)
    ap.add_argument("--renders", default="renders")
    ap.add_argument("--results", default="results")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    renders = Path(args.renders)
    out = Path(args.out or Path(args.results) / f"judge-{args.judge_label}.json")
    prior = {}
    if out.is_file():
        try:
            prior = {e["png"]: e for e in
                     json.loads(out.read_text())["evaluations"]}
        except Exception:
            prior = {}

    evaluations = []
    for label in LABELS:
        result_file = Path(args.results) / f"{label}.json"
        if not result_file.is_file():
            print(f"SKIP {label} (no result json)", flush=True)
            continue
        briefs = {r["task"]: r["brief"]
                  for r in json.loads(result_file.read_text())["results"]}
        for task, brief in briefs.items():
            png_path = renders / label / f"{task}.png"
            key = str(png_path)
            if key in prior:
                evaluations.append(prior[key])
                continue
            if not png_path.is_file():
                print(f"  {label}/{task}: no PNG, skipped", flush=True)
                continue
            png = png_path.read_bytes()
            t0 = time.time()
            verdict = judge_image(args.judge_base_url, args.judge_model,
                                  png, brief)
            verdict.update({"label": label, "task": task,
                            "png": key, "elapsed_s": round(time.time() - t0, 1)})
            evaluations.append(verdict)
            print(f"  {label}/{task}: score={verdict.get('score')} "
                  f"{(verdict.get('text') or '')[:80]}", flush=True)
            # Incremental save: a crash or restart keeps completed judgments.
            out.write_text(json.dumps(
                {"judge_label": args.judge_label, "judge_model": args.judge_model,
                 "n": len(evaluations), "partial": True,
                 "evaluations": evaluations}, indent=1))

    scored = [e for e in evaluations if e.get("score") is not None]
    report = {"judge_label": args.judge_label, "judge_model": args.judge_model,
              "n": len(evaluations), "n_scored": len(scored),
              "judge_mean": round(sum(e["score"] for e in scored) / len(scored), 2)
              if scored else None,
              "evaluations": evaluations}
    out.write_text(json.dumps(report, indent=1))
    print(f"JUDGE {args.judge_label}: {report['n_scored']}/{report['n']} scored, "
          f"mean {report['judge_mean']}")


if __name__ == "__main__":
    main()
