#!/usr/bin/env python3
"""IFEval runner for AIVA (scorecard edition).

Sends the 540 official google/IFEval prompts to any OpenAI-compatible
endpoint and scores responses with the official google-research scoring
code (vendored under official/, Apache-2.0). Reports both strict and
loose accuracy, exactly like the published leaderboard.

Usage:
    python ifeval_run.py http://127.0.0.1:8080/v1 MODEL LABEL [--think-off] [--limit N]
    # think-off adds chat_template_kwargs enable_thinking=false (Qwen models)
Results: results/ifeval_<label>.json + results/responses_<label>.jsonl
"""
import argparse
import hashlib
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

DATA = HERE / "data" / "ifeval_input.jsonl"
OUT = HERE / "results"
# Swift's Modal endpoint spends part of its generation budget on reasoning.
# Leave room for both that reasoning and the visible instruction-following answer.
MAX_TOKENS = 14_336
TEMPERATURE = 0.0
# Hard cap on thinking tokens per request (matches local router reasoning-budget=2048).
REASONING_BUDGET = int(os.environ.get("IF_EVAL_REASONING_BUDGET", "2048"))


# Hosted endpoints (e.g. a shared research API) rate-limit hard; a local
# llama-server never trips these. DELAY paces the request stream and RETRIES
# turn a 429/5xx into a backoff instead of an empty response that would
# silently score as a failure.
DELAY = float(os.environ.get("IF_EVAL_DELAY", "0"))
RETRIES = int(os.environ.get("IF_EVAL_RETRIES", "5"))
BACKOFF = float(os.environ.get("IF_EVAL_BACKOFF", "5"))
RETRYABLE = (429, 500, 502, 503, 504)


def _auth_headers():
    # Bearer token for gated endpoints (e.g. Modal-tunneled llama-server
    # launched with --api-key). Unset locally = current behavior.
    headers = {"Content-Type": "application/json"}
    if os.environ.get("OPENAI_API_KEY"):
        headers["Authorization"] = "Bearer " + os.environ["OPENAI_API_KEY"]
    return headers


def ask(args, prompt, timeout=900):
    body = {"model": args.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS, "stream": False}
    if args.reasoning_effort:
        body["reasoning_effort"] = args.reasoning_effort
    if args.think_off:
        body["chat_template_kwargs"] = {"enable_thinking": False}
    if REASONING_BUDGET and not args.think_off:
        body["reasoning_budget"] = REASONING_BUDGET
    req = urllib.request.Request(
        args.base_url + "/chat/completions", data=json.dumps(body).encode(),
        headers=_auth_headers())
    t0 = time.time()
    last = None
    for attempt in range(RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode())
            choice = data["choices"][0]
            msg = (choice.get("message") or {}).get("content")
            finish_reason = choice.get("finish_reason")
            # A model that runs into the configured generation cap still produced
            # an answer that the official scorer can evaluate; truncation is a
            # legitimate instruction-following failure, not a transport error.
            if finish_reason not in ("stop", "length") or not isinstance(msg, str) or not msg.strip():
                raise ValueError("Endpoint returned an empty or incomplete response")
            return msg, time.time() - t0, finish_reason
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    parser.add_argument("model")
    parser.add_argument("label", nargs="?")
    parser.add_argument("--think-off", action="store_true")
    parser.add_argument("--reasoning-effort",
                        choices=["minimal", "low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    args.base_url = args.base_url.rstrip("/")
    label = args.label or args.model
    if args.limit < 0 or Path(label).name != label or label in {".", ".."}:
        parser.error("Use a nonnegative limit and a label without directory components")

    dataset = DATA.read_bytes()
    inputs = E.read_prompt_list(str(DATA))
    if args.limit:
        inputs = inputs[:args.limit]
    expected = {item.prompt for item in inputs}
    config = {
        "protocol": 1, "dataset_sha256": hashlib.sha256(dataset).hexdigest(),
        "base_url_sha256": hashlib.sha256(args.base_url.encode()).hexdigest(),
        "model": args.model, "think_off": args.think_off, "limit": args.limit,
        "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS,
        "reasoning_budget": REASONING_BUDGET,
    }
    if args.reasoning_effort:
        config["reasoning_effort"] = args.reasoning_effort
    fingerprint = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()

    OUT.mkdir(parents=True, exist_ok=True)
    responses_path = OUT / f"responses_{label}.jsonl"
    have = {}
    needs_newline = False
    partial_offset = None
    if responses_path.is_file():
        with responses_path.open("rb") as checkpoint:
            while line := checkpoint.readline():
                offset = checkpoint.tell() - len(line)
                needs_newline = not line.endswith(b"\n")
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    if needs_newline:
                        partial_offset = offset
                        break  # Interrupted before completing the last record.
                    raise SystemExit("Invalid checkpoint record. Use a new label.")
                if not isinstance(record, dict) or record.get("fingerprint") != fingerprint:
                    raise SystemExit("Incompatible or historical checkpoint. Use a new label.")
                response = record.get("response")
                if not isinstance(response, str) or not response.strip():
                    raise SystemExit("Invalid checkpoint response. Use a new label.")
                prompt = record.get("prompt")
                if not isinstance(prompt, str) or prompt not in expected or prompt in have:
                    raise SystemExit("Unexpected or duplicate checkpoint prompt. Use a new label.")
                have[prompt] = response

    if partial_offset is not None:
        with responses_path.open("r+b") as checkpoint:
            checkpoint.truncate(partial_offset)
        needs_newline = False

    print(f"{label}: {len(inputs)} prompts, {len(have)} already complete", flush=True)
    t_start = time.time()
    truncated = 0
    with responses_path.open("a", encoding="utf-8") as checkpoint:
        for i, item in enumerate(inputs, 1):
            if item.prompt in have:
                continue
            try:
                text, elapsed, finish_reason = ask(args, item.prompt)
            except Exception as exc:
                print(f"  [{i}] request failed ({type(exc).__name__}); rerun to resume", flush=True)
                continue
            if finish_reason == "length":
                truncated += 1
            if needs_newline:
                checkpoint.write("\n")
                needs_newline = False
            checkpoint.write(json.dumps({"prompt": item.prompt, "response": text,
                                         "finish_reason": finish_reason,
                                         "fingerprint": fingerprint}) + "\n")
            checkpoint.flush()
            have[item.prompt] = text
            if DELAY:
                time.sleep(DELAY)
            if i % 20 == 0 or i == len(inputs):
                done = i
                remaining = len(inputs) - done
                rate = done / max(time.time() - t_start, 1e-6)
                eta = remaining / rate if rate > 0 else float("inf")
                pct = 100.0 * done / len(inputs)
                print(f"  [{i}/{len(inputs)}] {pct:5.1f}%  {elapsed:.0f}s  ETA {eta/60:.1f}m", flush=True)

    missing = sum(item.prompt not in have for item in inputs)
    if missing:
        raise SystemExit(f"Incomplete run: {missing} responses missing. No score written.")

    summary = {"label": label, "model": args.model, "n": len(inputs),
               "think_off": args.think_off, "run_fingerprint": fingerprint,
               "limit": args.limit, "smoke": bool(args.limit),
               "truncated": truncated}
    for name, func in [("strict", E.test_instruction_following_strict),
                       ("loose", E.test_instruction_following_loose)]:
        outputs = [func(inp, have) for inp in inputs]
        passed = sum(o.follow_all_instructions for o in outputs)
        acc = passed / len(outputs)
        summary[name] = round(acc, 4)
        print(f"{label} IFEval {name}: {acc:.4f} ({passed}/{len(outputs)})")
    summary["elapsed_s"] = round(time.time() - t_start, 1)
    score_name = "ifeval_smoke" if args.limit else "ifeval"
    (OUT / f"{score_name}_{label}.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print("SUMMARY " + json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
