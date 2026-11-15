# CanvasBench for Grace

A benchmark for the thing Grace actually does that no standard benchmark
measures: emit a structured sequence of canvas actions that renders into
something that matches the brief.

It is modelled on [Framer's CanvasBench](https://www.framer.com/canvasbench/)
(completion / steps / time / cost, with "good" and "great" tiers) and borrows
scene-graph metrics from Graphic Design Bench, but runs against Grace's own
`grace_canvas` library instead of a design tool.

## Why a custom harness

Grace's agent drives a 1000×650 vector canvas through the `canvas_draw` tool,
emitting JSON action sequences (`curve`, `path`, `rectangle`, `ellipse`,
`text`, `letter`, `style`, `move`, `delete`, `front`, `back`, …). It is not a
mouse-driven agent, it does not emit SVG, and it does not emit tldraw JSON --
so the matching public benchmarks (DrawingBench, Graphic Design Bench,
Sketch2Diagram) do not apply. CANVAS (KIXLAB) is the closest in interaction
mode and is open, but its tasks are mobile-UI design trees and its replication
task needs a reference image, which Grace never gets.

Everything here scores from the canvas engine's own state, so no reference
images and no human labels are needed.

## Running it

```bash
# one-off environment (does not touch the AIVA venv)
uv venv /tmp/canvas-bench-venv
uv pip install --python /tmp/canvas-bench-venv/bin/python cairosvg pillow

# a model must be served with the canvas_draw tool available
AGI_REPO=/path/to/AGi /tmp/canvas-bench-venv/bin/python benchmarks/canvas/canvas_bench.py \
    --base-url http://127.0.0.1:8080/v1 \
    --model ministral-3-14b-instruct-2512 \
    --label ministral3-14b \
    --out results/ministral.json \
    --out-dir renders/ministral
```

Useful flags: `--tier 1` (repeatable) to run one tier, `--limit N`,
`--temperature` (default 0), `--judge-base-url`/`--judge-model` to add an
optional multimodal judge that scores the rendered image against the brief.
When this scorecard checkout sits inside the AGi workspace, the harness finds
the AGi source checkout automatically; set `AGI_REPO` when it is elsewhere.

The system prompt is `canvas.engine.DRAW_INSTRUCTIONS` verbatim -- the same one
Grace uses in production -- so results transfer.

## Tasks

| Tier | What it probes | Example brief |
|---|---|---|
| 1 | single subject, real silhouette | "a single red apple with a stem and one leaf" |
| 2 | multi-object composition and light | "a still life: apple and cup on a wooden table" |
| 3 | layout, rhythm, hierarchy | "a nav bar with a logo and four evenly spaced items" |
| 4 | edit existing work, not repaint it | "make the leaf a brighter green" (seeded canvas) |
| 5 | draft, look at the render, improve it | scored on the delta between passes |

## Metrics

| Metric | Source |
|---|---|
| `check_score` | fraction of per-task checks passed |
| `tasks_fully_satisfied` | tasks where every check passed |
| `valid_rate` | `canvas.engine.validate_actions()` accepted the raw actions |
| `clamped_fields` | numeric fields the validator had to clamp into range |
| `render_rate` | `canvas.svg.render()` produced an SVG (and a PNG) |
| `truncated_rate` | the action JSON was cut off and needed recovery |
| `coverage` | fraction of canvas area covered by object boxes |
| `mean_overlap` | mean pairwise IoU of object boxes (excess = clutter) |
| `shared_baseline` | largest group of objects sharing a top edge (rhythm) |
| `even_spacing_run` | longest run of evenly spaced objects |
| `steps` | actions returned, and how many passes the task needed |
| `critique_delta` | tier 5: score after self-review minus score of the draft |
| `judge_mean` | optional VLM judge score for the rendered image |

Per-task checks live in `tasks.py` and run against the scene graph, so adding a
task or a check is a few lines. Each check returns `(ok, detail)` and failures
explain themselves in the JSON report.

## Notes

- The renderer is Grace's own (`canvas.svg.Renderer`), so `objects` is the same
  ordered list the browser console shows.
- Invalid actions are still rendered: the harness falls back to
  `engine.repair_model_actions()` exactly like `aiva_chat.node` does, so the
  visual metrics stay meaningful while `valid_rate` records the raw failure.
- `T3` checks are the CANVAS-style ones: rhythm and alignment rather than
  "is there a rectangle".
