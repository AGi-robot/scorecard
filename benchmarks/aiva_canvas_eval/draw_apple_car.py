#!/usr/bin/env python3
"""Draw apple + car on any canvas_draw-capable endpoint. Usage:
python draw_apple_car.py <base_url> <model> <out_prefix> [--no-think-off]
By default adds chat_template_kwargs enable_thinking=false (Qwen models);
pass --no-think-off to skip it (Ministral)."""
import json
import sys
import time
import urllib.request
from pathlib import Path

AGI_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(AGI_REPO / "capability" / "canvas" / "src"))
sys.path.insert(0, str(AGI_REPO / "capability" / "imaging" / "src"))
from canvas import DRAW_INSTRUCTIONS, DRAW_TOOL, engine, svg, completed_stream_actions
import cairosvg

BASE, MODEL, PREFIX = sys.argv[1], sys.argv[2], sys.argv[3]
THINK_OFF = "--no-think-off" not in sys.argv


def draw_tool(brief):
    messages = [{"role": "system", "content": DRAW_INSTRUCTIONS},
                {"role": "user", "content": [{"type": "text", "text": brief}]}]
    body = {"model": MODEL, "messages": messages, "temperature": 0.0,
            "max_tokens": 3072, "stream": False,
            "tools": [DRAW_TOOL], "parallel_tool_calls": False}
    if THINK_OFF:
        body["chat_template_kwargs"] = {"enable_thinking": False}
    req = urllib.request.Request(
        BASE.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=900) as r:
        data = json.loads(r.read().decode())
    data["_elapsed"] = time.time() - t0
    choice = data["choices"][0]
    msg = choice.get("message", {})
    raw = ""
    for call in msg.get("tool_calls") or []:
        raw = (call.get("function") or {}).get("arguments", "") or raw
    if not raw:
        raw = msg.get("content") or ""
    try:
        parsed = json.loads(raw)
        actions = parsed.get("actions", []) if isinstance(parsed, dict) else []
    except json.JSONDecodeError:
        actions = completed_stream_actions(raw)
    return actions, data, msg


def render_png(actions):
    renderer = svg.Renderer()
    for a in actions:
        try:
            renderer.apply(a)
        except Exception:
            pass
    return cairosvg.svg2png(
        bytestring=svg.render(renderer.objects, validate=False).encode())


TASKS = {
    "apple": ("Draw a single red apple with a short brown stem and one green "
              "leaf, sitting slightly left of centre. Draw it as a filled "
              "silhouette with color, not just an outline."),
    "car": ("Draw a simple side-view car: two black wheels at the bottom, a "
            "silver/grey body cabin, windows, and headlights. Use filled "
            "shapes with color, not just outlines."),
}

for name, brief in TASKS.items():
    print(f"=== {PREFIX} {name} ===", flush=True)
    actions, data, msg = draw_tool(brief)
    print(f"  actions={len(actions)} elapsed={data.get('_elapsed', 0):.1f}s "
          f"finish={data['choices'][0].get('finish_reason')}")
    for i, a in enumerate(actions):
        print(f"    {i}: {a.get('kind')} id={a.get('id')} "
              f"fill={a.get('fill_color')} color={a.get('color')} "
              f"points={len(a.get('points') or [])}")
    try:
        v = engine.validate_actions(actions)
        print(f"  VALID: {len(v)} actions")
    except Exception as e:
        print(f"  INVALID: {e}")
    png = render_png(actions)
    path = Path(__file__).resolve().parent / "renders" / f"{PREFIX}_{name}.png"
    path.write_bytes(png)
    print(f"  saved {path} ({len(png)} bytes)")
