#!/usr/bin/env python3
"""AIVA explainer-animation eval: model generates a single-HTML animated
"How Grace Works" diagram; automated checks verify structure + behaviour.

Usage (from diagnostic/scorecard):
  ../../AIVA/.venv/bin/python benchmarks/aiva_archie_eval/archie_eval.py \
    --base-url <openai-compatible /v1> --model <alias> \
    --output benchmarks/aiva_archie_eval/results/<label> --label <label>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROMPT = (HERE / "prompt.md").read_text()

REQUIRED_WORDS = ["webui", "rosbridge", "telepathy", "interactive",
                  "llama.cpp", "ministral", "memory", "canvas", "launch.sh"]
FORBIDDEN_WORDS = ["aurora", "cnc", "hrm"]  # separate system, must not appear
EXCLUSION_RE = r"separate|not part|not in|exclud|isn't|is not|outside|never|don't|do not|no .*pipeline"


def _forbidden_check(html_low: str, word: str) -> tuple[bool, str]:
    """Fail only on non-exclusion mentions: a note saying X 'is a separate
    system and is not part of this pipeline' is compliance, not a leak.
    Uses a character window around each mention (markup may split words
    like <b>AuRoRA</b> away from their sentence)."""
    import re
    bad = []
    for m in re.finditer(re.escape(word), html_low):
        window = html_low[max(0, m.start() - 200):m.end() + 200]
        if not re.search(EXCLUSION_RE, window):
            bad.append(window.strip().replace("\n", " ")[:120])
    if not bad:
        return True, "clean (exclusion notes allowed)"
    return False, f"{len(bad)} non-exclusion mention(s): {bad[0][:100]}"


def complete(base_url: str, model: str, api_key: str, max_tokens: int,
             timeout: int, out_dir, think_off: bool = False,
             reasoning_effort: str = "medium",
             no_reasoning_effort: bool = False,
             reasoning_budget: int | None = 4096) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    url = base_url.rstrip("/") + "/chat/completions"
    body = {"model": model, "temperature": 0, "top_p": 1,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": PROMPT}]}
    if think_off:
        # Qwen3-family (Swift): disable thinking for format-parity runs.
        body["chat_template_kwargs"] = {"enable_thinking": False}
    elif not no_reasoning_effort:
        # Native llama.cpp reasoning control (validated server-side against
        # the template's probed levels; unsupported values get a 400).
        # Ministral ignores it (non-thinking template); Swift honours
        # low/medium/xhigh, rejects minimal/high/max.
        body["reasoning_effort"] = reasoning_effort
    if reasoning_budget is not None and reasoning_budget >= 0:
        # Hard cap on <think> tokens; server closes the think block and
        # forces the answer when exhausted. Essential for long-output tasks
        # so thinking cannot eat the whole max_tokens budget.
        body["reasoning_budget_tokens"] = reasoning_budget
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    msg = data["choices"][0]["message"]
    text = msg.get("content", "")
    # save any stripped thinking trace for diagnostics (not scored)
    think = msg.get("reasoning_content", "")
    if think:
        (out_dir / "thinking.txt").write_text(think if isinstance(think, str) else json.dumps(think))
        print(f"[diag] saved {len(think)} chars of reasoning_content", flush=True)
    # strip accidental fences
    m = re.search(r"```(?:html)?\s*(.*?)```", text, re.S | re.I)
    return m.group(1).strip() if m else text.strip()


def static_checks(html: str) -> list[dict]:
    out = []
    low = html.lower()
    out.append({"name": "single_html_doctype",
                "ok": "<!doctype html" in low,
                "detail": "has <!DOCTYPE html>" if "<!doctype html" in low else "missing doctype"})
    # xmlns namespace identifiers (SVG/XHTML) are not network fetches
    ext = [u for u in re.finditer(r'https?://[^\s"\'<>]+', html)
           if not re.match(r'https?://www\.w3\.org/(2000/svg|1999/xhtml)', u.group(0))]
    out.append({"name": "no_external_urls", "ok": not ext,
                "detail": f"{len(ext)} external URL(s): {[u.group(0)[:60] for u in ext][:3]}" if ext else "fully inline"})
    for w in REQUIRED_WORDS:
        out.append({"name": f"mentions_{w.replace('.', '_').replace('/', '_')}",
                    "ok": w in low,
                    "detail": f"{'found' if w in low else 'MISSING'}: {w}"})
    for w in FORBIDDEN_WORDS:
        ok, detail = _forbidden_check(low, w)
        out.append({"name": f"excludes_{w}", "ok": ok,
                    "detail": f"{detail}: {w}"})
    has_anim = ("@keyframes" in low or "requestanimationframe" in low)
    out.append({"name": "has_animation", "ok": has_anim,
                "detail": "keyframes/rAF found" if has_anim else "no CSS/JS animation detected"})
    for ctl in ["play", "pause", "step", "restart"]:
        out.append({"name": f"control_{ctl}", "ok": ctl in low,
                    "detail": f"{'found' if ctl in low else 'MISSING'} button/label: {ctl}"})
    out.append({"name": "has_script_style",
                "ok": "<script" in low and "<style" in low,
                "detail": "inline <style>+<script>" if ("<script" in low and "<style" in low) else "missing inline style/script"})
    return out


def _stage_text(pg) -> str:
    """Best-effort read of the visible stage indicator."""
    for sel in ["text=/Stage\\s+\\d+\\s*\\/\\s*\\d+/i", "[data-stage]",
                ".stage-indicator", "#stage", "#stage-label"]:
        try:
            loc = pg.locator(sel).first
            if loc.count():
                t = (loc.inner_text(timeout=1500) or "").strip()
                if t:
                    return " ".join(t.split())[:80]
        except Exception:
            continue
    try:
        body = pg.content()
        import re
        m = re.search(r"Stage\s+\d+\s*/\s*\d+[^<]{0,60}", body, re.I)
        if m:
            return " ".join(m.group(0).split())[:80]
    except Exception:
        pass
    return ""


def _click_first(pg, sels, timeout=3000) -> bool:
    for sel in sels:
        try:
            loc = pg.locator(sel).first
            if loc.count():
                loc.click(timeout=timeout)
                return True
        except Exception:
            continue
    return False


PLAY_SELS = ["button:has-text('Play')", "button:has-text('play')",
             "#play", "[data-action='play']"]
STEP_SELS = ["button:has-text('Step')", "button:has-text('step')",
             "#step", "[data-action='step']"]


def browser_check(html_path: Path) -> dict:
    """Headless-Chromium functional check: zero console errors, controls
    advance the stage indicator (Play and Step both exercised)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ran": False, "ok": None,
                "detail": "playwright not installed; static checks only"}
    errors: list[str] = []
    notes: list[str] = []
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            try:
                pg = b.new_page(viewport={"width": 1280, "height": 800})
                pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                pg.on("pageerror", lambda e: errors.append(str(e)))
                pg.goto(f"file://{html_path.resolve()}", wait_until="load", timeout=30000)
                pg.wait_for_timeout(4000)
                before = _stage_text(pg)
                stepped = False
                if _click_first(pg, STEP_SELS):
                    pg.wait_for_timeout(1500)
                    after = _stage_text(pg)
                    stepped = bool(after) and after != before
                    notes.append(f"step: {before!r} -> {after!r}")
                else:
                    notes.append("step: no step control clickable")
                played = False
                if _click_first(pg, PLAY_SELS):
                    pg.wait_for_timeout(3000)
                    after_play = _stage_text(pg)
                    played = bool(after_play) and after_play != before
                    notes.append(f"play: {before!r} -> {after_play!r}")
                else:
                    notes.append("play: no play control clickable")
            finally:
                b.close()
    except Exception as e:
        return {"ran": True, "ok": False, "detail": f"browser launch/load failed: {e}"}
    ok_errors = not errors
    ok_func = stepped and played
    ok = ok_errors and ok_func
    detail = ("; ".join([
        "zero console errors" if ok_errors else f"{len(errors)} console error(s): {errors[:3]}",
        ("controls advance stage" if ok_func
         else f"controls STUCK (step={stepped}, play={played})"),
        *notes,
    ]))
    return {"ran": True, "ok": ok, "detail": detail}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--max-tokens", type=int, default=16384)
    ap.add_argument("--request-timeout", type=int, default=900)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--think-off", action="store_true", default=False,
                    help="disable thinking on Qwen-family models (overrides "
                         "--reasoning-effort)")
    ap.add_argument("--reasoning-effort", default="medium",
                    help="llama.cpp reasoning_effort (default: medium). "
                         "Swift honours low/medium/xhigh; Ministral ignores it.")
    ap.add_argument("--no-reasoning-effort", action="store_true", default=False,
                    help="omit the reasoning_effort field (for non-llama.cpp "
                         "backends like RustingStrata that may reject it)")
    ap.add_argument("--reasoning-budget", type=int, default=4096,
                    help="cap <think> tokens per request (llama.cpp "
                         "reasoning_budget_tokens; -1 = server default/unlimited)")
    a = ap.parse_args()
    import os
    api_key = a.api_key or os.environ.get("OPENAI_API_KEY", "EMPTY")

    a.output.mkdir(parents=True, exist_ok=True)
    print(f"[{a.label}] requesting explainer HTML from {a.model} ...", flush=True)
    html = complete(a.base_url, a.model, api_key, a.max_tokens,
                    a.request_timeout, a.output, a.think_off,
                    a.reasoning_effort, a.no_reasoning_effort,
                    a.reasoning_budget)
    html_path = a.output / f"{a.label}.html"
    html_path.write_text(html)
    print(f"[{a.label}] saved {len(html)/1024:.0f} KB -> {html_path}", flush=True)

    checks = static_checks(html)
    checks.append({"name": "browser_zero_errors", **browser_check(html_path)})
    passed = sum(1 for c in checks if c.get("ok") is True)
    failed = [c["name"] for c in checks if c.get("ok") is False]
    report = {"label": a.label, "model": a.model, "base_url": a.base_url,
              "bytes": len(html), "passed": passed, "total": len(checks),
              "failed": failed, "checks": checks}
    (a.output / f"{a.label}.checks.json").write_text(json.dumps(report, indent=2))
    (a.output / f"{a.label}.meta.json").write_text(json.dumps(
        {"model": a.model, "max_tokens": a.max_tokens,
         "reasoning_effort": None if (a.think_off or a.no_reasoning_effort)
         else a.reasoning_effort,
         "think_off": a.think_off, "prompt_sha256":
         __import__("hashlib").sha256(PROMPT.encode()).hexdigest()}, indent=2))
    print(f"[{a.label}] {passed}/{len(checks)} checks passed", flush=True)
    if failed:
        print(f"[{a.label}] FAILED: {failed}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
