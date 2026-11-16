#!/usr/bin/env python3
"""BFCL single-turn runner for Grace (scorecard edition).

Covers AST-checkable categories only: simple, multiple, parallel,
parallel_multiple, irrelevance. No environments, no judges.

Usage:
    python bfcl_run.py http://127.0.0.1:8080/v1 MODEL LABEL [--think-off] [--categories "simple parallel"] [--limit N]
Results: results/bfcl_<label>.json + results/responses_<label>.jsonl
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from bfcl_scoring import score_entry  # noqa: E402

BASE_URL = sys.argv[1].rstrip("/")
MODEL = sys.argv[2]
LABEL = sys.argv[3] if len(sys.argv) > 3 else MODEL
THINK_OFF = "--think-off" in sys.argv
CATS = None
LIMIT = 0
for i, a in enumerate(sys.argv):
    if a == "--categories" and i + 1 < len(sys.argv):
        CATS = sys.argv[i + 1].split()
    if a == "--limit" and i + 1 < len(sys.argv):
        LIMIT = int(sys.argv[i + 1])

ALL_CATS = ["simple", "multiple", "parallel", "parallel_multiple", "irrelevance"]
CATS = CATS or ALL_CATS

OUT = HERE / "results"
OUT.mkdir(parents=True, exist_ok=True)


def load_cat(cat):
    qs, ans = {}, {}
    for line in open(HERE / "data" / f"BFCL_v3_{cat}.json"):
        line = line.strip()
        if line:
            d = json.loads(line)
            qs[d["id"]] = d
    p = HERE / "data" / "possible_answer" / f"BFCL_v3_{cat}.json"
    if p.is_file():
        for line in open(p):
            line = line.strip()
            if line:
                d = json.loads(line)
                ans[d["id"]] = d.get("ground_truth", [])
    return qs, ans


def to_openai_tools(funcs):
    tools = []
    for f in funcs:
        params = f.get("parameters", {})
        props, req = {}, []
        if isinstance(params, dict):
            raw_props = params.get("properties", {})
            for k, v in raw_props.items():
                t = (v.get("type") or "string").lower()
                jt = {"integer": "integer", "float": "number", "boolean": "boolean",
                       "array": "array", "dict": "object", "object": "object",
                       "string": "string", "any": "string", "number": "number"}.get(t, "string")
                prop = {"type": jt}
                if v.get("description"):
                    prop["description"] = v["description"]
                if jt == "array" and isinstance(v.get("items"), dict):
                    prop["items"] = {"type": "string"}
                props[k] = prop
            req = params.get("required", [])
        tools.append({"type": "function", "function": {
            "name": f["name"], "description": f.get("description", ""),
            "parameters": {"type": "object", "properties": props, "required": req}}})
    return tools


def ask(messages, tools, timeout=300, max_tokens=1024):
    body = {"model": MODEL, "messages": messages, "temperature": 0.0,
            "max_tokens": max_tokens, "stream": False}
    if tools:
        body["tools"] = tools
        body["parallel_tool_calls"] = False
    if THINK_OFF:
        body["chat_template_kwargs"] = {"enable_thinking": False}
    req = urllib.request.Request(BASE_URL + "/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    msg = (data["choices"][0].get("message") or {})
    calls = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except Exception:
            args = {}
        calls.append({fn.get("name", ""): args})
    return calls, time.time() - t0


def main():
    print(f"{LABEL}: categories={CATS} -> {BASE_URL} (think_off={THINK_OFF})", flush=True)
    all_entries = []
    for cat in CATS:
        qs, ans = load_cat(cat)
        ids = sorted(qs.keys())
        if LIMIT:
            ids = ids[:LIMIT]
        for qid in ids:
            all_entries.append((cat, qid, qs[qid], ans.get(qid, [])))
    print(f"  total {len(all_entries)} prompts", flush=True)
    resp_path = OUT / f"responses_{LABEL}.jsonl"
    done = {}
    if resp_path.is_file():
        for line in open(resp_path):
            line = line.strip()
            if line:
                try:
                    r = json.loads(line)
                    done[r["id"]] = r
                except Exception:
                    pass
        print(f"  resuming: {len(done)} already done", flush=True)
    per_cat = {c: {"pass": 0, "total": 0} for c in CATS}
    with open(resp_path, "a") as f:
        for n, (cat, qid, q, gt) in enumerate(all_entries):
            if qid in done and done[qid].get("calls") is not None:
                ok = done[qid].get("ok", False)
                per_cat[cat]["total"] += 1
                per_cat[cat]["pass"] += 1 if ok else 0
                continue
            turns = q["question"]
            messages = turns[0] if isinstance(turns[0], list) else turns
            tools = to_openai_tools(q["function"])
            try:
                calls, el = ask(messages, tools)
            except Exception as e:
                print(f"  [{n}] {qid} error: {str(e)[:100]}", flush=True)
                calls, el = [], 0.0
            # irrelevance: ground truth empty -> pass iff no calls
            if cat == "irrelevance":
                ok = len(calls) == 0
            else:
                ok = score_entry(cat, calls, gt)
            per_cat[cat]["total"] += 1
            per_cat[cat]["pass"] += 1 if ok else 0
            f.write(json.dumps({"id": qid, "cat": cat, "calls": calls, "ok": ok}) + "\n")
            f.flush()
            if (n + 1) % 20 == 0:
                print(f"  [{n+1}/{len(all_entries)}] { {c: round(v['pass']/max(1,v['total']),3) for c,v in per_cat.items()} }", flush=True)
    summary = {"label": LABEL, "model": MODEL, "think_off": THINK_OFF, "per_category": {}}
    tot_p = tot_t = 0
    for c, v in per_cat.items():
        acc = v["pass"] / max(1, v["total"])
        summary["per_category"][c] = {"pass": v["pass"], "total": v["total"], "acc": round(acc, 4)}
        tot_p += v["pass"]
        tot_t += v["total"]
    summary["overall"] = round(tot_p / max(1, tot_t), 4)
    summary["overall_pass"] = f"{tot_p}/{tot_t}"
    json.dump(summary, open(OUT / f"bfcl_{LABEL}.json", "w"), indent=1)
    print("SUMMARY " + json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
