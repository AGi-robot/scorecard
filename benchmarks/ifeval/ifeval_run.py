#!/usr/bin/env python3
"""IFEval runner for Grace (scorecard edition).

Sends the 540 official google/IFEval prompts to any OpenAI-compatible
endpoint and scores responses with the official google-research scoring
code (vendored under official/, Apache-2.0). Reports both strict and
loose accuracy, exactly like the published leaderboard.

Usage:
    python ifeval_run.py http://127.0.0.1:8080/v1 MODEL LABEL [--think-off] [--limit N]
    # think-off adds chat_template_kwargs enable_thinking=false (Qwen models)
Results: results/ifeval_<label>.json + results/responses_<label>.jsonl
"""
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "official"))
from instruction_following_eval import evaluation_lib as E  # noqa: E402

BASE_URL = sys.argv[1].rstrip("/")
MODEL = sys.argv[2]
LABEL = sys.argv[3] if len(sys.argv) > 3 else MODEL
THINK_OFF = "--think-off" in sys.argv
LIMIT = 0
for i, a in enumerate(sys.argv):
    if a == "--limit" and i + 1 < len(sys.argv):
        LIMIT = int(sys.argv[i + 1])

# Hosted endpoints (e.g. a shared research API) rate-limit hard; a local
# llama-server never trips these. DELAY paces the request stream and RETRIES
# turn a 429/5xx into a backoff instead of an empty response that would
# silently score as a failure.
DELAY = float(os.environ.get("IF_EVAL_DELAY", "0"))
RETRIES = int(os.environ.get("IF_EVAL_RETRIES", "5"))
BACKOFF = float(os.environ.get("IF_EVAL_BACKOFF", "5"))
RETRYABLE = (429, 500, 502, 503, 504)

OUT = HERE / "results"
OUT.mkdir(parents=True, exist_ok=True)

PROMPTS = [json.loads(l) for l in
           open(HERE / "data" / "ifeval_input.jsonl")]
if LIMIT:
    PROMPTS = PROMPTS[:LIMIT]


def ask(prompt, timeout=900, max_tokens=2048):
    body = {"model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0, "max_tokens": max_tokens, "stream": False}
    if THINK_OFF:
        body["chat_template_kwargs"] = {"enable_thinking": False}
    req = urllib.request.Request(
        BASE_URL + "/chat/completions", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    last = None
    for attempt in range(RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode())
            msg = (data["choices"][0].get("message") or {}).get("content") or ""
            return msg, time.time() - t0
        except urllib.error.HTTPError as e:
            if e.code not in RETRYABLE or attempt == RETRIES:
                raise
            last = e
        except Exception as e:
            last = e
            if attempt == RETRIES:
                raise
        wait = BACKOFF * (2 ** attempt) + random.uniform(0, 1)
        print(f"    retry {attempt + 1}/{RETRIES} in {wait:.1f}s "
              f"({str(last)[:60]})", flush=True)
        time.sleep(wait)
    raise last


def main():
    responses_path = OUT / f"responses_{LABEL}.jsonl"
    print(f"{LABEL}: {len(PROMPTS)} prompts -> {BASE_URL} (think_off={THINK_OFF})",
          flush=True)
    t_start = time.time()
    # Resume on the PROMPT, not the line number: a request that failed (or
    # came back empty after a rate-limit) must be retried, while a later
    # prompt that succeeded must not be lost.
    have = {}
    if responses_path.is_file():
        for line in open(responses_path):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("response", "").strip():
                have[rec["prompt"]] = rec["response"]
        print(f"  resuming: {len(have)} already done", flush=True)
    with open(responses_path, "a") as f:
        for i, ex in enumerate(PROMPTS):
            if ex["prompt"] in have:
                continue
            try:
                text, el = ask(ex["prompt"])
            except Exception as e:
                print(f"  [{i}] request error: {str(e)[:100]}", flush=True)
                text, el = "", 0.0
            f.write(json.dumps({"prompt": ex["prompt"],
                                "response": text}) + "\n")
            f.flush()
            if DELAY:
                time.sleep(DELAY)
            if (i + 1) % 20 == 0:
                print(f"  [{i+1}/{len(PROMPTS)}] {el:.0f}s "
                      f"(elapsed {time.time()-t_start:.0f}s)", flush=True)

    inputs = E.read_prompt_list(str(HERE / "data" / "ifeval_input.jsonl"))
    if LIMIT:
        inputs = inputs[:LIMIT]
    prompt_to_response = E.read_prompt_to_response_dict(str(responses_path))
    summary = {"label": LABEL, "model": MODEL, "n": len(inputs),
               "think_off": THINK_OFF}
    for name, func in [("strict", E.test_instruction_following_strict),
                       ("loose", E.test_instruction_following_loose)]:
        outputs = [func(inp, prompt_to_response) for inp in inputs]
        acc = sum(o.follow_all_instructions for o in outputs) / len(outputs)
        summary[name] = round(acc, 4)
        print(f"{LABEL} IFEval {name}: {acc:.4f} "
              f"({sum(o.follow_all_instructions for o in outputs)}/{len(outputs)})")
    summary["elapsed_s"] = round(time.time() - t_start, 1)
    json.dump(summary, open(OUT / f"ifeval_{LABEL}.json", "w"), indent=1)
    print("SUMMARY " + json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
