#!/usr/bin/env python3
"""Grace Canvas Eval: score a model on Grace's own vector canvas.

Runs the drawing tasks in tasks.py against any OpenAI-compatible endpoint that
speaks the canvas_draw tool, then scores the resulting scene graph with the
automatic checks. Everything is scored from the canvas engine's own state, so
no reference images or human labels are needed.

Usage:
    python grace_canvas_eval.py --base-url http://127.0.0.1:8080/v1 \\
        --model ministral-3-14b-instruct-2512 --label ministral

Options:
    --tier 1,2,3,4,5     only run these tiers (repeatable)
    --judge-base-url U   optional multimodal judge to score the rendered image
    --out PATH           JSON report path
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

def find_agi_repo():
    """Find the AGi checkout that provides canvas and imagegen source."""
    configured = os.environ.get("AGI_REPO")
    if configured:
        candidates = [Path(configured).expanduser().resolve()]
    else:
        candidates = list(Path(__file__).resolve().parents)
    for candidate in candidates:
        if (candidate / "canvas" / "src").is_dir() and (candidate / "imaging" / "src").is_dir():
            return candidate
    raise SystemExit(
        "Could not find the AGi source checkout (canvas/src and imaging/src). "
        "Set AGI_REPO to its path."
    )


AGI_REPO = find_agi_repo()
sys.path.insert(0, str(AGI_REPO / "canvas" / "src"))
sys.path.insert(0, str(AGI_REPO / "imaging" / "src"))

import cairosvg  # noqa: E402
from canvas import DRAW_INSTRUCTIONS, DRAW_TOOL, engine, svg  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tasks as T  # noqa: E402

try:  # optional: enables the raster 'image' kind
    from imagegen import register_image_kind
    register_image_kind()
except Exception:
    pass


# ------------------------------------------------------------------ curve rule
# The most common model mistake: a curve needs exactly 1+3n points
# (4, 7, 10, ... 31): one start point plus triples of cubic control/endpoint.
# Models obey machine-validated constraints far better than prose in the system
# prompt, so this constraint exists in two forms below.
CURVE_RULE_PROSE = (
    "CURVE POINT RULE (strict): a curve's points array must hold exactly "
    "1 + 3n points -- one of 4, 7, 10, 13, 16, 19, 22, 25, 28 or 31. The "
    "FIRST point is the start; every following triple is control1, control2, "
    "endpoint. Never emit 3, 5, 6, 9, 12 or 15 points."
)

CURVE_POINT_COUNTS = [4, 7, 10, 13, 16, 19, 22, 25, 28, 31]


def build_tool(schema_hint=False):
    """canvas_draw tool. With schema_hint the curve point constraint is made
    machine-visible (minItems + explicit allowed counts) instead of prose-only."""
    tool = json.loads(json.dumps(DRAW_TOOL))
    if schema_hint:
        points = tool["function"]["parameters"]["properties"][
            "actions"]["items"]["properties"]["points"]
        points["minItems"] = 4
        points["description"] = (
            "Curve: start followed by control1, control2, endpoint for each "
            "cubic segment. The count must be exactly one of "
            f"{', '.join(map(str, CURVE_POINT_COUNTS))} points (start + "
            "triples of control/endpoint). Other paths: connected points. "
            "Max 31 points per pass."
        )
    return tool

# ------------------------------------------------------------------ model ---
def chat(base_url, model, messages, tools=None, temperature=0.0, max_tokens=3072,
         timeout=900, think_off=False):
    body = {"model": model, "messages": messages, "temperature": temperature,
            "max_tokens": max_tokens, "stream": False}
    if think_off:
        # Thinking models (Qwen3.x/Swift): a reasoning trace burns into the
        # token budget and can truncate the tool call, so disable it for
        # output-format parity with models that have no thinking mode.
        body["chat_template_kwargs"] = {"enable_thinking": False}
    if tools:
        body["tools"] = tools
        body["parallel_tool_calls"] = False
    req = urllib_request(base_url, body, timeout)
    return req


def urllib_request(base_url, body, timeout):
    import urllib.request
    url = base_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = json.loads(response.read().decode())
    data["_elapsed"] = time.time() - t0
    return data


def draw_actions(base_url, model, system, user, images=None, temperature=0.0,
                 schema_hint=False, think_off=False):
    """One canvas_draw turn. Returns (actions, meta)."""
    content = [{"type": "text", "text": user}]
    for image in images or []:
        content.insert(0, {"type": "image_url",
                           "image_url": {"url": "data:image/png;base64," + image}})
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": content}]
    data = chat(base_url, model, messages, tools=[build_tool(schema_hint)],
                temperature=temperature, think_off=think_off)
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    usage = data.get("usage") or {}
    raw = ""
    for call in message.get("tool_calls") or []:
        raw = (call.get("function") or {}).get("arguments", "") or raw
    if not raw:
        raw = message.get("content") or ""

    truncated = False
    try:
        parsed = json.loads(raw)
        actions = parsed.get("actions", []) if isinstance(parsed, dict) else []
    except json.JSONDecodeError:
        truncated = True
        recovered = engine.completed_stream_actions(raw)
        try:
            parsed = json.loads(json.dumps({"actions": recovered}))
            actions = recovered
        except Exception:
            actions = recovered

    meta = {
        "elapsed_s": round(data.get("_elapsed", 0.0), 2),
        "completion_tokens": usage.get("completion_tokens"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "truncated": truncated,
        "raw_len": len(raw),
        "raw_tail": raw[-200:] if truncated else "",
        "finish_reason": choice.get("finish_reason"),
        "response": (message.get("content") or "")[:400],
        "more": bool(parsed.get("more")) if isinstance(parsed, dict) else False,
    }
    return actions, meta


# ------------------------------------------------------------------ scene ---
def build_scene(actions):
    """Replay actions onto the canvas renderer and summarise the result."""
    renderer = svg.Renderer()
    for action in actions:
        try:
            renderer.apply(action)
        except Exception:
            continue
    scene = {"objects": renderer.objects}
    return scene


def scene_metrics(scene):
    return {
        "objects": len(scene["objects"]),
        "kinds": T.scene_kinds(scene),
        "colours": T.scene_colours(scene),
        "texts": T.scene_texts(scene),
        "coverage": round(T.coverage(scene), 4),
        "mean_overlap": round(T.mean_overlap(scene), 4),
        "shared_baseline": T.shared_baseline(scene),
        "even_spacing_run": T.even_spacing(scene),
    }


def validate_and_measure(raw_actions):
    """Validate, and count how many numeric fields had to be clamped."""
    try:
        validated = engine.validate_actions(raw_actions)
        valid, error = True, None
    except Exception as exc:
        valid, error = False, str(exc)
        try:
            validated = engine.validate_actions(engine.repair_model_actions(raw_actions))
        except Exception:
            validated = []
    clamped = 0
    for raw, checked in zip(raw_actions, validated or []):
        for key, value in raw.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if key in checked and checked[key] != value:
                    clamped += 1
    return validated, valid, error, clamped


def render_png(actions):
    try:
        markup = svg.render(actions, validate=False)
        return cairosvg.svg2png(bytestring=markup.encode()), None
    except Exception as exc:
        return None, str(exc)


# ------------------------------------------------------------------ judge ---
def judge_image(judge_url, judge_model, png_bytes, brief, timeout=300):
    encoded = base64.b64encode(png_bytes).decode()
    body = {"model": judge_model, "temperature": 0.0, "max_tokens": 120,
            "messages": [{"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": "data:image/png;base64," + encoded}},
                {"type": "text", "text":
                    f'The image was drawn for this request: "{brief}"\n'
                    "Does the image fulfil the request? Answer with a score from 0 to 10, "
                    "then one short sentence of justification."}]}]}
    try:
        data = urllib_request(judge_url, body, timeout)
        text = (data["choices"][0]["message"].get("content") or "").strip()
        score = None
        digits = ""
        for char in text:
            if char.isdigit():
                digits += char
                if len(digits) == 2:
                    break
            elif digits:
                break
        if digits:
            score = min(10, int(digits))
        return {"score": score, "text": text[:400]}
    except Exception as exc:
        return {"score": None, "text": f"judge error: {exc}"}


# ------------------------------------------------------------------- main ---
def run_task(task, args):
    system = DRAW_INSTRUCTIONS
    seed = task.get("seed_actions") or []
    user = task["brief"]
    if seed:
        state = engine.canvas_context(build_scene(seed)["objects"])
        user = f"Current canvas state:\n{state}\n\n{user}"

    actions, meta = draw_actions(args.base_url, args.model, system, user,
                                 schema_hint=args.schema_hint,
                                 temperature=args.temperature)
    validated, valid, error, clamped = validate_and_measure(actions)
    scene = build_scene(validated)
    png, render_error = render_png(validated)

    checks = []
    for check in task["checks"]:
        try:
            if check.__code__.co_argcount > 1:
                ok, detail = check(scene, actions)
            else:
                ok, detail = check(scene)
        except Exception as exc:
            ok, detail = False, f"check error: {exc}"
        checks.append({"check": getattr(check, "check_name", check.__name__),
                       "ok": bool(ok), "detail": detail})

    result = {
        "task": task["id"], "tier": task["tier"], "tier_name": T.TIERS[task["tier"]],
        "brief": task["brief"],
        "actions_returned": len(actions),
        "steps": len(actions),
        "valid": valid, "validation_error": error, "clamped_fields": clamped,
        "rendered": png is not None, "render_error": render_error,
        "truncated_stream": meta["truncated"], "meta": meta,
        "scene": scene_metrics(scene),
        "checks": checks,
        "checks_passed": sum(1 for c in checks if c["ok"]),
        "checks_total": len(checks),
    }
    result["score"] = result["checks_passed"] / max(1, result["checks_total"])

    if png and args.judge_base_url:
        verdict = judge_image(args.judge_base_url, args.judge_model, png, task["brief"])
        result["judge"] = verdict

    if args.out_dir:
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        if png:
            (out / f"{task['id']}.png").write_bytes(png)
        (out / f"{task['id']}.actions.json").write_text(json.dumps(actions, indent=1))

    # Tier 5: show the draft, let the model critique and improve it.
    if task["tier"] == 5 and png:
        state = engine.canvas_context(build_scene(validated)["objects"])
        critique = ("Here is a rendered screenshot of the canvas as it currently looks. "
                    "Review it against the request: inspect silhouette, proportions, overlap, "
                    "spacing, palette, lighting and focal point. Remove or replace stray "
                    "marks and malformed shapes, then add the detail needed to make the "
                    "image read as intentional finished artwork.\n\n"
                    f"The request was: {task['brief']}\n\n"
                    f"Current canvas state:\n{state}")
        edit_actions, edit_meta = draw_actions(
            args.base_url, args.model, system, critique,
            images=[base64.b64encode(png).decode()],
            schema_hint=args.schema_hint,
            temperature=args.temperature)
        edit_validated, edit_valid, edit_error, edit_clamped = validate_and_measure(edit_actions)
        edit_scene = build_scene(edit_validated)
        edit_png, _ = render_png(edit_validated)
        edit_checks = []
        for check in task["checks"]:
            try:
                ok, detail = check(edit_scene) if check.__code__.co_argcount <= 1 else check(edit_scene, edit_actions)
            except Exception as exc:
                ok, detail = False, f"check error: {exc}"
            edit_checks.append({"check": getattr(check, "check_name", check.__name__),
                                 "ok": bool(ok), "detail": detail})
        passed = sum(1 for c in edit_checks if c["ok"])
        result["pass2"] = {
            "steps": len(edit_actions), "valid": edit_valid, "clamped_fields": edit_clamped,
            "truncated_stream": edit_meta["truncated"],
            "elapsed_s": edit_meta["elapsed_s"],
            "checks_passed": passed, "checks_total": len(edit_checks),
            "score": passed / max(1, len(edit_checks)),
            "scene": scene_metrics(edit_scene),
            "checks": edit_checks,
        }
        result["critique_delta"] = result["pass2"]["score"] - result["score"]
        if args.out_dir and edit_png:
            (Path(args.out_dir) / f"{task['id']}.pass2.png").write_bytes(edit_png)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--label", default="model")
    parser.add_argument("--tier", type=int, action="append", default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--judge-base-url", default=None)
    parser.add_argument("--judge-model", default=None)
    parser.add_argument("--schema-hint", action="store_true", default=False,
                        help="put the curve point-count rule in the tool schema "
                             "(machine-validated) instead of prose-only")
    parser.add_argument("--out", default=None)
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()

    selected = [t for t in T.TASKS if args.tier is None or t["tier"] in args.tier]
    if args.limit:
        selected = selected[:args.limit]

    print(f"Grace Canvas Eval: {args.label} ({len(selected)} tasks)", flush=True)
    results = []
    for task in selected:
        started = time.time()
        try:
            result = run_task(task, args)
        except Exception as exc:
            result = {"task": task["id"], "tier": task["tier"], "error": str(exc),
                      "score": 0.0, "checks_passed": 0, "checks_total": len(task["checks"])}
        result["wall_s"] = round(time.time() - started, 2)
        results.append(result)
        print(f"  {task['id']:<22} {result.get('checks_passed', 0)}/{result.get('checks_total', 0)}"
              f"  valid={result.get('valid')} rendered={result.get('rendered')}"
              f"  steps={result.get('steps')}  {result['wall_s']}s", flush=True)

    total_checks = sum(r.get("checks_total", 0) for r in results)
    passed_checks = sum(r.get("checks_passed", 0) for r in results)
    perfect = sum(1 for r in results if r.get("checks_total") and
                  r.get("checks_passed") == r.get("checks_total"))
    deltas = [r["critique_delta"] for r in results if "critique_delta" in r]
    summary = {
        "label": args.label, "model": args.model, "schema_hint": args.schema_hint,
        "base_url": args.base_url,
        "tasks": len(results),
        "check_score": round(passed_checks / max(1, total_checks), 4),
        "tasks_fully_satisfied": perfect,
        "fully_satisfied_rate": round(perfect / max(1, len(results)), 4),
        "valid_rate": round(sum(1 for r in results if r.get("valid")) / max(1, len(results)), 4),
        "render_rate": round(sum(1 for r in results if r.get("rendered")) / max(1, len(results)), 4),
        "truncated_rate": round(sum(1 for r in results if r.get("truncated_stream")) / max(1, len(results)), 4),
        "mean_steps": round(sum(r.get("steps", 0) for r in results) / max(1, len(results)), 2),
        "total_wall_s": round(sum(r.get("wall_s", 0) for r in results), 1),
        "critique_delta": round(sum(deltas) / len(deltas), 4) if deltas else None,
    }
    judge_scores = [r["judge"]["score"] for r in results
                    if r.get("judge") and r["judge"].get("score") is not None]
    if judge_scores:
        summary["judge_mean"] = round(sum(judge_scores) / len(judge_scores), 2)

    report = {"summary": summary, "results": results}
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=1))
    print("\nSUMMARY " + json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
