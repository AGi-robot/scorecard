#!/usr/bin/env python3
"""EQ-Bench v2 runner for Grace (scorecard edition).

Uses the EQ-Bench v2 full-scale scoring protocol: temperature 0.01,
max_tokens 60, up to 3 attempts per question until the answer parses,
no-revise mode. Scoring uses the official lib/scoring.py (vendored here as
eqbench_scoring.py, MIT licensed -- see LICENSE.EQ-Bench-MIT), so numbers
are directly comparable with published EQ-Bench v2 leaderboard scores.

The 171 questions live in data/eq_bench_v2_questions_171.json (from the
EQ-Bench repo, same license).

Usage:
    python eqbench_run.py http://127.0.0.1:8080/v1 MODEL_NAME LABEL
    # e.g. LABEL=ministral3-14b
Results: results/eqbench_v2_<LABEL>.json

Why v2 and not v4: EQ-Bench v4 grades multi-turn roleplays with an LLM
judge, which means the judge -- not the test -- becomes the measurement
instrument. For a local, deterministic, leaderboard-comparable screen of
emotion recognition, v2's reference-scored intensity ratings are the
right tool. Revisit v4 if a judged active-EQ signal is ever needed
(and budget a judge at least as strong as the models under test).
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
sys.path.insert(0, str(HERE))
from eqbench_scoring import parse_answers, calculate_score_fullscale, calculate_eq_bench_score  # noqa: E402

BASE_URL = sys.argv[1].rstrip("/")
MODEL = sys.argv[2]
LABEL = sys.argv[3] if len(sys.argv) > 3 else MODEL
THINK_OFF = "--think-off" in sys.argv

# Hosted endpoints rate-limit hard; a local llama-server never trips these.
# DELAY paces the request stream and RETRIES turn a 429/5xx into a backoff
# instead of a parse failure that silently costs a question.
DELAY = float(os.environ.get("EQBENCH_DELAY", "0"))
RETRIES = int(os.environ.get("EQBENCH_RETRIES", "5"))
BACKOFF = float(os.environ.get("EQBENCH_BACKOFF", "5"))
RETRYABLE = (429, 500, 502, 503, 504)

# Keep v2 outputs separate from earlier runs that used legacy normalized (v1) scoring.
OUT = HERE / "results" / f"eqbench_v2_{LABEL}.json"


def remove_revision_instructions(prompt):
    """Official EQ-Bench behavior: strip the critique/revised-score block so
    the model outputs ONLY the four first-pass scores (matches the 60-token
    budget and keeps the regex parser to exactly 4 emotions)."""
    prompt = prompt.replace(
        " Then critique your answer by thinking it through step by step. Finally, give your revised scores.",
        "")
    prompt = prompt.replace("First pass scores:\n", "")
    prompt = (prompt[:prompt.find("Critique: <your critique here>")] + "\n"
              + prompt[prompt.find("[End of answer]"):])
    prompt += "\nYour answer:\n"
    return prompt


def ask(prompt, timeout=300):
    body = {"model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.01, "max_tokens": 60, "stream": False}
    if THINK_OFF:
        # Qwen3.x thinking models: 60 tokens can't fit a thinking trace,
        # so the answer never arrives. Disable thinking for a direct
        # answer-vs-answer comparison (same protocol as our blind tests).
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
            return (data["choices"][0].get("message") or {}).get("content", ""), time.time() - t0
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
    OUT.parent.mkdir(parents=True, exist_ok=True)
    questions = json.loads((HERE / "data" / "eq_bench_v2_questions_171.json").read_text())
    ids = sorted(questions, key=lambda x: int(x))
    print(f"{LABEL}: {len(ids)} questions (think_off={THINK_OFF})", flush=True)

    indiv = {}
    fails = 0
    t_start = time.time()
    for i, qid in enumerate(ids):
        q = questions[qid]
        ref = q["reference_answer"]
        ok = False
        for attempt in range(3):
            try:
                text, el = ask(remove_revision_instructions(q["prompt"]))
                first, _ = parse_answers(text, False)
                score = calculate_score_fullscale(ref, first)
                if score is None:
                    continue
                indiv[qid] = {"first_pass_answers": first,
                              "first_pass_score": score, "revised_score": None,
                              "attempts": attempt + 1, "secs": round(el, 1)}
                ok = True
                break
            except Exception as e:
                print(f"  [{qid}] attempt {attempt+1} error: {str(e)[:100]}", flush=True)
                time.sleep(2)
        if not ok:
            fails += 1
            indiv[qid] = {"first_pass_answers": None,
                          "first_pass_score": None, "revised_score": None,
                          "attempts": 3, "secs": 0}
        if (i + 1) % 20 == 0:
            done = [v["first_pass_score"] for v in indiv.values()
                    if v["first_pass_score"] is not None]
            print(f"  [{i+1}/{len(ids)}] running mean: "
                  f"{100*sum(done)/len(done)/10:.1f} (parse fails so far: {fails})",
                  flush=True)
        if DELAY:
            time.sleep(DELAY)

    results = {"eqbench": {
        "run_metadata": {"total_iterations": 1, "model": MODEL,
                         "label": LABEL, "benchmark": "EQ-Bench v2",
                         "scoring": "official full-scale",
                         "think_off": THINK_OFF},
        "iterations": {"0": {"individual_scores_fullscale": indiv}}}}
    avg, parseable = calculate_eq_bench_score("eqbench", results, str(OUT), fullscale=True)
    print(f"\n{LABEL} EQ-Bench v2 score: {avg}  "
          f"(parseable {parseable}/{len(ids)}, {time.time()-t_start:.0f}s total)")


if __name__ == "__main__":
    main()
