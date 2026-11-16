#!/usr/bin/env python3
"""Grace Chatbot Eval: blind preference comparison (single rater).

Phase 1 --generate: plays each conversation script against every contestant
model and stores the transcripts with the identities sealed.
Phase 2 --rate: shows each script's transcripts side by side as anonymous
"Model A" / "Model B" (order randomized per pair) and records the rater's
preference on warmth, coherence, persona, and overall.
Phase 3 --score: win rates per dimension plus Elo standings.

Contestants are OpenAI-compatible endpoints, e.g.:
    python preference_bench.py --generate \\
        --contestant ministral=http://127.0.0.1:8080/v1/ministral-3-14b-instruct-2512 \\
        --contestant swift1.5-qwen3.8-27B=http://127.0.0.1:8081/v1/swift

The configured contestant label should identify the exact model build; an
endpoint may continue to use a shorter API model ID.

The system prompt defaults to Grace's SOUL.md plus the current timestamp --
the same context aiva_chat/node.py builds -- so this tests the deployment,
not the bare model. Pass --bare to test models without the persona.

Nothing runs until you invoke it; generation needs the servers up.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import itertools
import json
import random
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import scripts as SCRIPTS_MOD  # noqa: E402

OUT_DIR = HERE / "results"
DIMENSIONS = ["warmth", "coherence", "persona", "overall"]
CHOICES = {"a": "A", "b": "B", "t": "tie", "s": "skip"}


def load_soul():
    for cand in [
        Path("/home/oppa-ai/AGi/AIVA/persona/SOUL.md"),
    ]:
        if cand.is_file():
            return cand.read_text(encoding="utf-8")
    return "You are Grace, a warm, honest AI companion."


def chat(base_url, model, messages, temperature=0.7, max_tokens=512,
         think_off=False, timeout=600):
    body = {"model": model, "messages": messages, "temperature": temperature,
            "max_tokens": max_tokens, "stream": False}
    if think_off:
        body["chat_template_kwargs"] = {"enable_thinking": False}
    url = base_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode())


def parse_contestant(spec):
    """name=url/model -- model is the part after the last slash of the URL."""
    name, rest = spec.split("=", 1)
    base_url, _, model = rest.rstrip("/").rpartition("/")
    if not model:
        raise ValueError(f"bad contestant spec (need .../v1/model-name): {spec}")
    base_url = base_url or rest
    return {"name": name, "base_url": base_url, "model": model}


def play_script(script, contestant, system, temperature, think_off):
    messages = [{"role": "system", "content": system}]
    transcript = []
    for turn in script["turns"]:
        if "user" not in turn:
            continue
        messages.append({"role": "user", "content": turn["user"]})
        try:
            data = chat(contestant["base_url"], contestant["model"], messages,
                        temperature=temperature, think_off=think_off)
            reply = (data["choices"][0].get("message") or {}).get("content", "")
        except Exception as exc:
            reply = f"[ERROR: {exc}]"
        transcript.append({"user": turn["user"], "reply": reply,
                           "expect": turn.get("expect", "")})
        messages.append({"role": "assistant", "content": reply})
    return transcript


def cmd_generate(args):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    contestants = [parse_contestant(s) for s in args.contestant]
    if len(contestants) < 1:
        raise SystemExit("need at least one --contestant entry")
    soul = "" if args.bare else load_soul()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%A, %B %d, %Y at %I:%M %p UTC")
    system = (soul + f"\n\nCurrent local date and time: {stamp}. "
              "Use this as the authoritative current time.").strip()
    batch = {"created": stamp, "bare": args.bare, "temperature": args.temperature,
             "think_off": args.think_off, "contestants": [c["name"] for c in contestants],
             "scripts": {}}
    for script in SCRIPTS_MOD.SCRIPTS:
        if args.script and script["id"] not in args.script:
            continue
        print(f"--- {script['id']}: {script['title']} ---", flush=True)
        batch["scripts"][script["id"]] = {
            "title": script["title"], "probe": script["probe"],
            "transcripts": {}}
        for c in contestants:
            print(f"    {c['name']} ...", flush=True)
            t = play_script(script, c, system, args.temperature, args.think_off)
            batch["scripts"][script["id"]]["transcripts"][c["name"]] = t
            time.sleep(1)
    digest = hashlib.sha256(json.dumps(batch, sort_keys=True).encode()).hexdigest()[:8]
    path = OUT_DIR / f"batch_{digest}.json"
    path.write_text(json.dumps(batch, indent=1, ensure_ascii=False))
    print(f"\nwrote {path} ({len(contestants)} contestants x "
          f"{len(batch['scripts'])} scripts)")
    print("Identities are sealed inside; raters only ever see A/B.")


def cmd_rate(args):
    batches = sorted(OUT_DIR.glob("batch_*.json"))
    if not batches:
        raise SystemExit("no batches -- run --generate first")
    batch_path = Path(args.batch) if args.batch else batches[-1]
    batch = json.loads(batch_path.read_text())
    names = batch["contestants"]
    pairs = list(itertools.combinations(names, 2))
    votes_path = batch_path.with_name(batch_path.stem + "_votes.jsonl")

    seen = set()
    if votes_path.is_file():
        for line in votes_path.read_text().splitlines():
            try:
                v = json.loads(line)
                seen.add((v["script"], v["left"], v["right"]))
            except Exception:
                continue

    rng = random.Random()
    order = [(s, a, b) for s in batch["scripts"] for (a, b) in pairs]
    rng.shuffle(order)
    print(f"{len(order)} comparisons ({len(order) - len([o for o in order if (o[0], o[1], o[2]) in seen or (o[0], o[2], o[1]) in seen])} remaining)\n")
    print("For each pair: which reply set is better?  a = left, b = right, t = tie, s = skip\n")
    print("HOW TO READ EACH ROUND:")
    print("  - The >>> RATER NOTE lines tell you what each script was built to test.")
    print("    Read them BEFORE judging that reply -- they say what to look for.")
    print("  - Vote all four dimensions every round; ties (t) are always allowed.\n")

    with votes_path.open("a") as log:
        for script_id, left, right in order:
            if (script_id, left, right) in seen or (script_id, right, left) in seen:
                continue
            script = batch["scripts"][script_id]
            flip = rng.random() < 0.5
            first, second = (right, left) if flip else (left, right)
            print(f"===== {script_id}: {script['title']}  (probe: {script['probe']}) =====")
            for t in script["transcripts"][first]:
                print(f"\n  you: {t['user']}")
                print(f"  A : {t['reply']}")
                if t.get("expect"):
                    print(f"  >>> RATER NOTE: {t['expect']}")
            for t in script["transcripts"][second]:
                print(f"\n  you: {t['user']}")
                print(f"  B : {t['reply']}")
                if t.get("expect"):
                    print(f"  >>> RATER NOTE: {t['expect']}")
            print()
            vote = {"script": script_id, "left": first, "right": second, "batch": batch_path.name}
            for dim in DIMENSIONS:
                while True:
                    ans = input(f"  {dim:9s} [a/b/t/s]: ").strip().lower()
                    if ans in CHOICES:
                        break
                vote[dim] = CHOICES[ans]
                if ans == "s":
                    break
            if vote.get(DIMENSIONS[0]) == "skip":
                print("  skipped\n")
                continue
            log.write(json.dumps(vote, ensure_ascii=False) + "\n")
            log.flush()
            print()
    print(f"\nvotes appended to {votes_path}")
    print("Run --score to compute standings.")


def elo_expected(ra, rb):
    return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))


def cmd_score(args):
    batches = sorted(OUT_DIR.glob("batch_*.json"))
    if not batches:
        raise SystemExit("no batches")
    batch_path = Path(args.batch) if args.batch else batches[-1]
    votes_path = batch_path.with_name(batch_path.stem + "_votes.jsonl")
    if not votes_path.is_file():
        raise SystemExit("no votes yet -- run --rate first")

    K = 32.0
    elos = {}
    wins = {}
    totals = {}

    def name_of(n):
        elos.setdefault(n, 1500.0)
        wins.setdefault(n, {d: 0.0 for d in DIMENSIONS})
        totals.setdefault(n, 0)
        return n

    n_votes = 0
    for line in votes_path.read_text().splitlines():
        v = json.loads(line)
        left, right = name_of(v["left"]), name_of(v["right"])
        totals[left] += 1
        totals[right] += 1
        n_votes += 1
        for dim in DIMENSIONS:
            pick = v.get(dim)
            if pick == "skip":
                continue
            if pick == "tie":
                sa = sb = 0.5
                wins[left][dim] += 0.5
                wins[right][dim] += 0.5
            elif pick == "A":
                sa, sb = 1.0, 0.0
                wins[left][dim] += 1.0
            else:
                sa, sb = 0.0, 1.0
                wins[right][dim] += 1.0
            if dim == "overall":
                ea = elo_expected(elos[left], elos[right])
                elos[left] += K * (sa - ea)
                elos[right] += K * (sb - (1.0 - ea))

    print(f"\n{n_votes} blind comparisons from {votes_path.name}\n")
    print(f"{'model':<24} {'elo':>7} {'n':>4}  " +
          "  ".join(f"{d[:4]:>7}" for d in DIMENSIONS))
    for name in sorted(elos, key=elos.get, reverse=True):
        cells = "  ".join(
            f"{wins[name][d] / max(1, totals[name]):>6.0%}" for d in DIMENSIONS)
        print(f"{name:<24} {elos[name]:>7.0f} {totals[name]:>4}  {cells}")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    gen = sub.add_parser("generate", help="play scripts against all contestants")
    gen.add_argument("--contestant", action="append", required=True,
                     help="name=url/model, repeatable (need >= 2)")
    gen.add_argument("--script", action="append", default=None,
                     help="only run these script ids (default: all)")
    gen.add_argument("--temperature", type=float, default=0.7)
    gen.add_argument("--think-off", action="store_true", default=False,
                     help="disable thinking on Qwen models (BFCL protocol parity)")
    gen.add_argument("--bare", action="store_true", default=False,
                     help="no SOUL persona; bare-model comparison")
    rate = sub.add_parser("rate", help="blind human rating")
    rate.add_argument("--batch", default=None)
    score = sub.add_parser("score", help="win rates + Elo standings")
    score.add_argument("--batch", default=None)
    args = parser.parse_args()
    {"generate": cmd_generate, "rate": cmd_rate, "score": cmd_score}[args.cmd](args)


if __name__ == "__main__":
    main()
