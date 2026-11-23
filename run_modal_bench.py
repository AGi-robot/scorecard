#!/usr/bin/env python3
"""Launch a scorecard benchmark against a chosen model endpoint.

Pairs the two Modal servers (benchmark-only) or the local AGi router
with any harness under diagnostic/scorecard/benchmarks/.

Interactive:
    python3 run_modal_bench.py

Direct:
    python3 run_modal_bench.py --model ministral --bench ifeval [--limit 50] [--dry-run]
    python3 run_modal_bench.py --model swift --bench canvas --task T1-lighthouse

Key: sourced from ~/.config/agi/modal-bench.env (OPENAI_API_KEY) or env.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE / "benchmarks"

MODELS = {
    "ministral": {
        "base_url": "https://oppa-ai-org--grace-llm-serve-serve-ministral.us-east.modal.run/v1",
        "model": "ministral-3-8b-instruct-2512-abliterated",
        "label": "ministral-modal-abliterated",
        "desc": "Modal 8B chat model (fast, cheap) — instruction-following first",
    },
    "swift": {
        "base_url": "https://oppa-ai-org--grace-llm-serve-serve-swift.us-east.modal.run/v1",
        "model": "swift15-qwen3.8-27b-local",
        "label": "swift-modal",
        "desc": "Modal 27B reasoning model (slow cold-start, MTP) — tools/canvas",
    },
    "local": {
        "base_url": "http://127.0.0.1:8080/v1",
        "model": "ministral-3-8b-instruct-2512-abliterated",
        "label": "local-router",
        "desc": "Local AGi router (free, instant) — baseline comparison",
    },
}

BENCHES = {
    "ifeval": {
        "group": "official",
        "name": "IFEval",
        "script": BENCH / "ifeval" / "ifeval_run.py",
        "desc": "541 prompts, official strict/loose scoring",
        "args": lambda m, o: [m["base_url"], m["model"], f"{m['label']}-ifeval"]
        + (["--limit", str(o.limit)] if o.limit else [])
        + (["--think-off"] if o.think_off else []),
        "env": {"IF_EVAL_RETRIES": "8"},
        "note": "Start here on ministral: cheapest full validation of the Modal path.",
    },
    "canvas": {
        "group": "grace",
        "name": "Canvas Eval",
        "script": BENCH / "grace_canvas_eval" / "grace_canvas_eval.py",
        "desc": "Vector canvas, protocol v4; checks + optional judge",
        "args": lambda m, o: [
            "--base-url", m["base_url"], "--model", m["model"],
            "--label", f"{m['label']}-canvas",
            "--out", str(HERE / "benchmarks" / "grace_canvas_eval" / "results" / f"{m['label']}-canvas.json"),
            "--out-dir", str(HERE / "benchmarks" / "grace_canvas_eval" / "renders" / f"{m['label']}-canvas"),
        ] + (["--task", o.task] if o.task else [])
        + (["--limit", str(o.limit)] if o.limit else [])
        + (["--single-pass"] if o.single_pass else []),
        "env": {},
        "note": "Swift's home turf (MTP + reasoning). Production defaults are baked in.",
    },
    "longmemeval": {
        "group": "official",
        "name": "LongMemEval",
        "script": BENCH / "longmemeval" / "full_history_run.py",
        "desc": "Long-context memory, ICLR 2025 500Q (needs --input data file)",
        "args": lambda m, o: [
            "--base-url", m["base_url"], "--model", m["model"],
            "--input", o.input or "benchmarks/longmemeval/data/longmemeval.json",
            "--output", str(HERE / "benchmarks" / "longmemeval" / f"hypo_{m['label']}.jsonl"),
        ] + (["--limit", str(o.limit)] if o.limit else []),
        "env": {},
        "note": "Needs the official data file at --input. Heavy on Swift (32K ctx).",
    },
    "ifbench": {
        "group": "official",
        "name": "IFBench",
        "script": BENCH / "ifbench" / "ifbench_run.py",
        "desc": "AllenAI IFBench, pinned data+verifiers, single+multi-turn",
        "args": lambda m, o: [
            "--base-url", m["base_url"], "--model", m["model"],
            "--output", str(HERE / "benchmarks" / "ifbench" / f"results_{m['label']}"),
        ] + (["--limit", str(o.limit)] if o.limit else []),
        "env": {},
        "note": "Shares the baseline_common runner (needs --output dir).",
    },
    "livecodebench": {
        "group": "official",
        "name": "LiveCodeBench",
        "script": BENCH / "livecodebench" / "livecodebench_run.py",
        "desc": "Pinned rev 28fef95, code generation + execution",
        "args": lambda m, o: [
            "--base-url", m["base_url"], "--model", m["model"],
            "--output", str(HERE / "benchmarks" / "livecodebench" / f"results_{m['label']}"),
        ] + (["--limit", str(o.limit)] if o.limit else []),
        "env": {},
        "note": "Executes model code; needs the pinned official checkout (auto-cloned).",
    },
    "evalplus": {
        "group": "official",
        "name": "EvalPlus",
        "kind": "module",
        "module": "evalplus.codegen",
        "desc": "HumanEval+ / MBPP+ greedy codegen (--dataset)",
        "args": lambda m, o: [
            "--model", m["model"], "--dataset", o.dataset,
            "--backend", "openai", "--base-url", m["base_url"],
            "--greedy", "--root",
            str(HERE / "benchmarks" / "evalplus" / "results" / f"{m['label']}-{o.dataset}"),
        ],
        "env": {},
        "note": "Needs the evalplus pip package. Datasets: humaneval, mbpp.",
    },
    "eqbench": {
        "group": "official",
        "name": "EqBench",
        "kind": "guide",
        "desc": "eqbench-v4 + creative-writing-v3 (needs official checkout + judges)",
        "guide": (
            "EqBench is not one-click: it needs an official checkout ($EQ_WORK),\n"
            "a reference pool copy, and external judge models (Gemini/GPT/Claude).\n"
            "Suites: eqbench-v4, creative-writing-v3.\n"
            "Your evaluated model id for --evaluated-model / --test-model:\n"
            "  MODEL_ID"
        ),
        "note": "See benchmarks/eqbench/README.md for the full protocol.",
    },
    "safety": {
        "group": "grace",
        "name": "Companion Safety",
        "kind": "guide",
        "desc": "Companion behavior + boundaries (no runner yet)",
        "guide": "Planned only — benchmarks/companion_safety/README.md tracks readiness.\nNo runnable harness to launch yet.",
        "note": None,
    },
    "bfcl": {
        "group": "official",
        "name": "BFCL",
        "script": BENCH / "bfcl" / "mind_memory_run.py",
        "desc": "Tool-calling, aiva v4 harness (needs --mind-root checkout)",
        "args": lambda m, o: [
            "--base-url", m["base_url"], "--model", m["model"],
            "--label", f"{m['label']}-bfcl",
        ] + (["--mind-root", o.mind_root] if o.mind_root else [])
        + (["--limit", str(o.limit)] if o.limit else []),
        "env": {},
        "note": "Requires a Mind repo checkout (--mind-root). Swift recommended.",
    },
}


GROUPS = [("official", "OFFICIAL STANDARDS"), ("grace", "GRACE CUSTOM")]

def pick(options: dict, title: str) -> str:
    print(f"\n{title}")
    numbered: dict[int, str] = {}
    if all("group" not in v for v in options.values()):
        for i, (k, v) in enumerate(options.items(), 1):
            numbered[i] = k
            print(f"  {i}. {v.get('name', k)} — {v['desc']}")
    else:
        i = 0
        for gkey, gname in GROUPS:
            members = [(k, v) for k, v in options.items() if v.get("group", "grace") == gkey]
            if not members:
                continue
            if gkey != GROUPS[0][0]:
                print()
            print(f"  -- {gname} --")
            for k, v in members:
                i += 1
                numbered[i] = k
                print(f"  {i}. {v.get('name', k)} — {v['desc']}")
    while True:
        try:
            return numbered[int(input("Choice [1]: ").strip() or "1")]
        except (ValueError, KeyError):
            print("Invalid choice, try again.")


def check_key() -> bool:
    if os.environ.get("OPENAI_API_KEY") or os.environ.get("AIVA_LLM_API_KEY"):
        return True
    print("No API key in env. Run: source ~/.config/agi/modal-bench.env")
    return False


def preflight(base_url: str, timeout: int = 120) -> bool:
    """Fail fast: confirm the endpoint answers before launching 500 prompts."""
    url = base_url.rstrip("/") + "/health"
    headers = {}
    key = os.environ.get("OPENAI_API_KEY") or os.environ.get("AIVA_LLM_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            print(f"preflight {url} -> {r.status} OK")
            return True
    except Exception as e:
        print(f"preflight FAILED ({url}): {str(e)[:120]}")
        print("If this is first touch, the container is cold-loading — wait and retry.")
        return False


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--model", choices=list(MODELS) + ["custom"])
    p.add_argument("--base-url", help="with --model custom")
    p.add_argument("--model-id", help="model alias with --model custom")
    p.add_argument("--bench", choices=list(BENCHES))
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--think-off", action="store_true",
                   help="ifeval/canvas: run a separate thinking-disabled variant")
    p.add_argument("--task", help="canvas task id, e.g. T1-lighthouse")
    p.add_argument("--single-pass", action="store_true", help="canvas: one pass (quick A/B)")
    p.add_argument("--input", help="longmemeval data file")
    p.add_argument("--mind-root", help="bfcl Mind checkout")
    p.add_argument("--dataset", default="humaneval",
                   help="evalplus dataset (humaneval|mbpp)")
    p.add_argument("--eq-suite", default="eqbench-v4",
                   help="eqbench suite to describe")
    p.add_argument("--dry-run", action="store_true", help="print command, don't run")
    p.add_argument("--skip-preflight", action="store_true")
    o = p.parse_args()

    if o.model == "custom":
        if not (o.base_url and o.model_id):
            p.error("--model custom needs --base-url and --model-id")
        m = {"base_url": o.base_url, "model": o.model_id,
             "label": "custom", "desc": "custom endpoint"}
    else:
        m = MODELS[o.model or pick(MODELS, "Which model endpoint?")]
    b = BENCHES[o.bench or pick(BENCHES, "Which benchmark?")]
    if b.get("kind") not in ("guide", "module") and not b["script"].exists():
        sys.exit(f"harness missing: {b['script']}")
    if b.get("note"):
        print(f"note: {b['note']}")

    if not check_key():
        sys.exit(1)
    # Canvas + longmemeval also accept OPENAI_API_KEY; mirror AIVA key if needed.
    if not os.environ.get("OPENAI_API_KEY") and os.environ.get("AIVA_LLM_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ["AIVA_LLM_API_KEY"]

    if not o.skip_preflight and m["base_url"].startswith("http"):
        if not preflight(m["base_url"]):
            sys.exit(1)

    if b.get("kind") == "guide":
        print("\n" + b["guide"].replace("MODEL_ID", m["model"]))
        if b.get("note"):
            print(b["note"])
        return
    if b.get("kind") == "module":
        cmd = [sys.executable, "-m", b["module"]] + b["args"](m, o)
    else:
        cmd = [sys.executable, str(b["script"])] + b["args"](m, o)
    env = dict(os.environ)
    env.update({k: str(v) for k, v in b.get("env", {}).items()})
    print("\n$ " + " ".join(cmd))
    if o.dry_run:
        return
    r = subprocess.run(cmd, env=env)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
