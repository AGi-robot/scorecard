# TEST PROMPT — paste to the agentic model (or sent automatically by archie_eval.py)

Generate ONE single self-contained HTML file (inline CSS + JS, no external
network requests, system fonts only) that renders a PROFESSIONAL-LOOKING
ANIMATED EXPLAINER titled "How Grace Works" for the AIVA PC companion runtime.

## Architecture you must depict (exactly this pipeline, left → right)

1. **User** — speaks/types in the browser.
2. **Console WebUI** (browser-local appearance prefs; runtime config is read-only).
3. **rosbridge** WebSocket at 127.0.0.1:9090.
4. **telepathy_receptor** — ROS 2 adapter node.
5. **Interactive conversation engine** — uses persona (SOUL.md) + user profile (USER.md).
6. **llama.cpp router** — exactly ONE llama-server process, config
   models/llama-router.ini, routes by model name on port 8080:
   - Ministral 3 8B chat
   - voyage-4-nano embeddings
7. **Mind ConversationStore** — SQLite memory (recent/add_exchange, 8-turn window).
8. **Sidecars**: vector **Canvas** + **Imaging** capabilities, health/agi_logging.
9. **Response path** back through the same chain to the WebUI.
10. A caption: orchestrated by **AIVA/launch.sh** (builds shell workspace,
    starts router + rosbridge + chat + telepathy). AuRoRA is a separate
    system — do NOT show AuRoRA/CNC/TIC/HRM.

## Required features (all will be automatically checked)

- Dark professional theme, clean typography, generous whitespace, legend.
- Animated packets/dots flowing along connectors from User → WebUI → rosbridge
  → telepathy_receptor → interactive engine → llama.cpp router → Ministral,
  with a side-branch animation to Memory and Canvas, then response packets
  flowing back.
- Controls that WORK: **Play / Pause / Restart / Step** buttons plus a stage
  indicator (e.g. "Stage 3/9: telepathy_receptor"). Stepping must advance one
  stage at a time; Play must auto-advance with smooth animation.
- Each stage node shows a 1-line description tooltip/label.
- Responsive: readable at 1280×800 without scrolling sideways.
- Zero console errors when opened in a browser.

## Quality bar (judge-scored 1–5 each)

Layout · typography · colour/professionalism · motion smoothness ·
flow clarity (a newcomer understands the request path) · legend/labels.

## Constraints

- Single HTML file only. Inline `<style>` and `<script>`.
- No external URLs (no CDN, no fonts, no images). No `fetch()` to network.
- Vanilla JS or inline SVG/Canvas animation. CSS `@keyframes` and/or
  `requestAnimationFrame` expected.
- Must include (case-insensitive) the words: WebUI, rosbridge, telepathy,
  interactive, llama.cpp, Ministral, memory, Canvas, launch.sh.

Return ONLY the HTML file contents, no markdown fences, no commentary.
