#!/usr/bin/env python3
"""Standardized scorecard across every benchmark suite in this repo.

Prints one row per (model, benchmark) with every metric normalized to a
0-100 scale so suites with different units (percent, Elo, fraction) can be
read side by side.

Usage:
    python scorecard_all.py
"""
import glob
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def pct(x):
    return "n/a" if x is None else f"{x * 100:.1f}"


def load_json(p):
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return None


def rows():
    out = []

    # Pinned official baselines stay separate; smoke subsets are never ranked.
    for directory in ("ifbench", "livecodebench"):
        for p in sorted((HERE / directory / "results").glob("*/summary.json")):
            d = load_json(p)
            if not d or not d.get("full_run"):
                continue
            coding = directory == "livecodebench"
            notes = "pass@1 / pass@5" if coding else "prompt loose / strict"
            if not coding and "generation" in d:
                notes += (f"; cap {d['max_tokens']}; token-limited {d['generation']['token_limited']}"
                          f"; timeouts {d['generation']['timed_out']}")
            out.append({
                "bench": d["suite"], "model": d["model"], "n": d["n"],
                "strict": pct(d.get("pass@1" if coding else "prompt_loose")),
                "loose": pct(d.get("pass@5" if coding else "prompt_strict")),
                "extra": notes,
            })

    # --- IFEval: strict/loose accuracy -------------------------------
    for p in sorted(glob.glob(str(HERE / "ifeval" / "results" / "ifeval_*.json"))):
        d = load_json(p)
        if not d or d.get("smoke") or Path(p).name.startswith("ifeval_smoke_"):
            continue
        out.append({
            "bench": "IFEval",
            "model": d.get("label", "?"),
            "n": d.get("n"),
            "strict": pct(d.get("strict")),
            "loose": pct(d.get("loose")),
            "extra": f"{d.get('elapsed_s', 0) / 60:.0f} min",
        })

    # --- Historical EQ-Bench v2: final score ------------------------------------
    for p in sorted(glob.glob(str(HERE / "eqbench" / "results" / "eqbench_v2_*.json"))):
        d = load_json(p)
        if not d:
            continue
        try:
            it = d["eqbench"]["iterations"]
            key = sorted(it.keys())[0]
            res = it[key]["benchmark_results_fullscale"]
            score = res.get("final_score")
            parse = res.get("final_parseable")
            total = len(it[key]["individual_scores_fullscale"])
        except Exception:
            score, parse, total = None, None, None
        out.append({
            "bench": "EQ-Bench v2",
            "model": d["eqbench"]["run_metadata"].get("label", "?"),
            "n": total,
            "strict": pct(score / 100 if score is not None else None),
            "loose": "-",
            "extra": f"parseable {parse}/{total}" if parse else "",
        })

    # --- AIVA Chatbot Eval: Elo + win rates -------------------------
    votes = []
    for p in sorted(glob.glob(str(HERE / "aiva_chatbot_eval" / "results" / "*votes*.jsonl"))):
        for line in open(p):
            line = line.strip()
            if not line:
                continue
            try:
                votes.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    if votes:
        # last vote wins per (script, left, right, batch)
        seen = {}
        for v in votes:
            seen[(v.get("script"), v.get("left"), v.get("right"), v.get("batch"))] = v
        tally = {}
        elo = {}
        for v in seen.values():
            left, right = v["left"], v["right"]
            for model in (left, right):
                tally.setdefault(model, {"w": 0, "n": 0, "dims": {}})
                elo.setdefault(model, 1500.0)
            for dim in ("warmth", "coherence", "persona", "overall"):
                pick = v.get(dim)
                if pick not in ("A", "B", "tie"):
                    continue
                sa = 0.5 if pick == "tie" else float(pick == "A")
                for model, score in ((left, sa), (right, 1 - sa)):
                    t = tally[model]
                    d = t["dims"].setdefault(dim, {"w": 0, "n": 0})
                    d["w"] += score
                    d["n"] += 1
                    if dim == "overall":
                        t["w"] += score
                        t["n"] += 1
                if dim == "overall":
                    expected = 1 / (1 + 10 ** ((elo[right] - elo[left]) / 400))
                    elo[left] += 32 * (sa - expected)
                    elo[right] += 32 * ((1 - sa) - (1 - expected))
        for model, t in sorted(tally.items(), key=lambda kv: -elo.get(kv[0], 1500)):
            wr = t["w"] / t["n"] if t["n"] else 0
            dims = " ".join(
                f"{d[:4]} {v['w']}/{v['n']}" for d, v in sorted(t["dims"].items()))
            out.append({
                "bench": "Chatbot (Elo)",
                "model": model,
                "n": t["n"],
                "strict": f"Elo {elo.get(model, 1500):.0f}",
                "loose": f"{wr * 100:.0f}% win",
                "extra": dims,
            })

    # --- AIVA Canvas Eval: check_score / valid_rate ------------------
    for p in sorted(glob.glob(str(HERE / "aiva_canvas_eval" / "results" / "*.json"))):
        d = load_json(p)
        if not d:
            continue
        out.append({
            "bench": "Canvas Eval",
            "model": d.get("label", Path(p).stem),
            "n": d.get("n_tasks") or d.get("n"),
            "strict": pct(d.get("check_score")),
            "loose": pct(d.get("valid_rate")),
            "extra": f"full {d.get('tasks_fully_satisfied')}, render {pct(d.get('render_rate'))}",
        })
    return out


def render_markdown(r):
    """Render the collected rows as the scorecard report body."""
    lines = []
    by_bench = {}
    for x in r:
        by_bench.setdefault(x["bench"], []).append(x)
    for bench, items in by_bench.items():
        lines.append(f"### {bench}\n")
        lines.append("| Model | n | Primary | Secondary | Notes |")
        lines.append("|---|---:|---:|---:|---|")
        for x in items:
            lines.append(f"| {x['model']} | {x['n'] or '-'} | {x['strict']} | "
                         f"{x['loose']} | {x['extra']} |")
        lines.append("")
    return "\n".join(lines)


def main():
    r = rows()
    if not r:
        print("no results found")
        return
    if "--markdown" in sys.argv:
        out = sys.argv[sys.argv.index("--markdown") + 1] \
            if "--markdown" in sys.argv and \
            sys.argv.index("--markdown") + 1 < len(sys.argv) else None
        text = render_markdown(r)
        if out:
            with open(out, "w") as f:
                f.write(text)
            print(f"wrote {out}")
        else:
            print(text)
        return
    hdr = f"{'benchmark':<16}{'model':<28}{'n':>5}  {'primary':<12}{'secondary':<12}notes"
    print(hdr)
    print("-" * len(hdr))
    for x in r:
        print(f"{x['bench']:<16}{x['model']:<28}{str(x['n'] or '-'):>5}  "
              f"{str(x['strict']):<12}{str(x['loose']):<12}{x['extra']}")


if __name__ == "__main__":
    main()
