# AIVA "How Grace Works" explainer-animation eval

Agentic test: the model must generate a **single self-contained HTML file**
that renders a **professional-looking animated explainer** of how Grace
(AIVA PC runtime) works today. No external network dependencies.

## Pipeline under test (ground truth, Nov 2026)

```
User ──▶ Console WebUI (browser-local)
  ──▶ rosbridge WebSocket 127.0.0.1:9090
  ──▶ telepathy_receptor (ROS 2 adapter)
  ──▶ interactive conversation engine (persona SOUL.md + USER.md)
       ├──▶ llama.cpp router — ONE llama-server, models/llama-router.ini
       │     routes by model name: Ministral 3 8B chat + voyage-4-nano embeddings (:8080)
       └──▶ Mind ConversationStore (SQLite memory: recent/add_exchange)
  ──▶ sidecars: vector Canvas + Imaging capabilities, health/agi_logging
──▶ response returns along the same path to the WebUI
```

`AIVA/launch.sh` orchestrates everything: builds the shell workspace,
starts the router, rosbridge, chat nodes, and telepathy. `AIVA/.venv` is the
single Python env. AuRoRA (CNC/TIC/HRM) is a **separate** launch path and must
NOT appear in the animation.

## Scoring

Automated checks (pass/fail, in `archie_eval.py`):
1. Single `.html` file, inline CSS/JS, no `http(s)://` asset references.
2. Loads in headless Chromium with **zero console errors**.
3. Contains all required stage labels (case-insensitive):
   `WebUI`, `rosbridge`, `telepathy`, `interactive`, `llama.cpp`,
   `Ministral`, `memory`, `Canvas`.
4. Has working controls: Play/Pause + Step (buttons wired to JS).
5. Has real animation: `@keyframes` or `requestAnimationFrame` + animated
   packet/dot travelling the pipeline (not a static diagram).
6. Mentions `launch.sh` as the orchestrator somewhere.

Judge-scored 1–5 (LLM-as-judge or human, rubric in `prompt.md`):
layout, typography, colour/professionalism, motion smoothness,
flow clarity, legend/labels.

## Usage

```bash
# from diagnostic/scorecard, with the consolidated venv:
../../AIVA/.venv/bin/python benchmarks/aiva_archie_eval/archie_eval.py \
  --base-url https://oppa-ai-org--grace-llm-serve-serve-ministral.us-east.modal.run/v1 \
  --model ministral-3-8b-instruct-2512-abliterated \
  --output benchmarks/aiva_archie_eval/results/<label> \
  --label ministral-modal-explainer
```

Output: `<label>.html`, `<label>.checks.json`, `<label>.meta.json`.
Screenshots/contact sheet: open the HTML in Chromium and capture,
or reuse `../aiva_canvas_eval/contact_sheet.py` conventions.
