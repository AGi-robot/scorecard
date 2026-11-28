#!/usr/bin/env python3
"""Rescore canvas eval runs after an engine change, without rerunning models.

Replays each run's saved raw model actions (renders/<label>/<task>.actions.json)
through the current engine: validate -> repair -> scene -> checks -> render.
Updates results/<label>.json in place (same schema the runner writes) and
rewrites the PNGs. Prints before/after check_score per run.

Usage:
    python rescore.py [--label LABEL] [--renders renders] [--results results]
"""
import argparse
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tasks as T  # noqa: E402
from aiva_canvas_eval import (validate_and_measure, build_scene, render_png,
                               run_task  # noqa: F401  (keeps import surface stable)
                               )


def rescore_task(raw_actions, task, seed):
    validated, valid, error, clamped = validate_and_measure(raw_actions)
    base = seed if seed else []
    scene = build_scene(base + validated)
    png, render_error = render_png(base + validated)
    checks = []
    for check in task["checks"]:
        try:
            if check.__code__.co_argcount > 1:
                ok, detail = check(scene, raw_actions)
            else:
                ok, detail = check(scene)
            checks.append({"check": getattr(check, "check_name", check.__name__),
                           "ok": bool(ok), "detail": detail})
        except Exception as exc:
            checks.append({"check": getattr(check, "check_name", check.__name__),
                           "ok": False, "detail": f"check error: {exc}"})
    return {
        "task": task["id"], "tier": task["tier"], "tier_name": T.TIERS[task["tier"]],
        "brief": task["brief"], "actions_returned": len(raw_actions),
        "steps": len(raw_actions), "valid": valid, "validation_error": error,
        "clamped_fields": clamped, "rendered": png is not None,
        "render_error": render_error, "truncated_stream": False,
        "scene": {"n_objects": len(scene.get("objects", []))},
        "checks": checks, "checks_passed": sum(1 for c in checks if c["ok"]),
        "checks_total": len(checks),
        "score": sum(1 for c in checks if c["ok"]) / max(1, len(checks)),
    }, validated, png


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default=None)
    ap.add_argument("--renders", default="renders")
    ap.add_argument("--out-dir", default="renders")
    ap.add_argument("--results", default="results")
    args = ap.parse_args()

    renders = Path(args.renders)
    results = Path(args.results)
    labels = [args.label] if args.label else sorted(
        p.name for p in renders.iterdir()
        if p.is_dir() and p.name != "sheets" and (p / "T1-apple.actions.json").is_file())
    for label in labels:
        rp = results / f"{label}.json"
        if not rp.is_file():
            print(f"{label}: no results file, skip")
            continue
        d = json.load(open(rp))
        key = "results" if "results" in d else "tasks"
        new_rs = []
        for r in d.get(key, []):
            ap_ = renders / label / f"{r['task']}.actions.json"
            if not ap_.is_file():
                new_rs.append(r)
                continue
            try:
                raw = json.load(open(ap_))
            except Exception:
                new_rs.append(r)
                continue
            task = next(t for t in T.TASKS if t["id"] == r["task"])
            seed = task.get("seed_actions") or []
            try:
                nr, validated, png = rescore_task(raw, task, seed)
            except Exception as e:
                print(f"  {label}/{r['task']}: rescore failed: {e}")
                new_rs.append(r)
                continue
            nr["wall_s"] = r.get("wall_s", 0)
            # keep pass2/critique blocks from the original run untouched
            for k in ("pass2", "pass2_png", "judge", "meta", "error", "elapsed"):
                if k in r:
                    nr[k] = r[k]
            new_rs.append(nr)
            out = Path(args.out_dir) / label
            out.mkdir(parents=True, exist_ok=True)
            if png:
                (out / f"{r['task']}.png").write_bytes(png)
        tc = sum(r.get("checks_total", 0) for r in new_rs)
        pc = sum(r.get("checks_passed", 0) for r in new_rs)
        pf = sum(1 for r in new_rs if r.get("checks_total")
                 and r.get("checks_passed") == r.get("checks_total"))
        old = d.get("summary", {}).get("check_score")
        s = d.setdefault("summary", {})
        s.update({
            "check_score": round(pc / max(1, tc), 4),
            "tasks_fully_satisfied": pf,
            "fully_satisfied_rate": round(pf / max(1, len(new_rs)), 4),
            "valid_rate": round(sum(1 for r in new_rs if r.get("valid")) / max(1, len(new_rs)), 4),
            "render_rate": round(sum(1 for r in new_rs if r.get("rendered")) / max(1, len(new_rs)), 4),
            "truncated_rate": round(sum(1 for r in new_rs if r.get("truncated_stream")) / max(1, len(new_rs)), 4),
            "mean_steps": round(sum(r.get("steps", 0) for r in new_rs) / max(1, len(new_rs)), 2),
        })
        d[key] = new_rs
        json.dump(d, open(rp, "w"), indent=1)
        print(f"{label}: check {old} -> {s['check_score']}  "
              f"valid {s['valid_rate']}  render {s['render_rate']}")


if __name__ == "__main__":
    main()
