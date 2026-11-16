# Scorecard

Shared model benchmark suites for AGi projects.

## Benchmarks

See the [benchmark index](benchmarks/README.md) for current coverage, the
[agent and self-coding roadmap](benchmarks/agentic/README.md), and the
[companion behavior benchmark status](benchmarks/companion_safety/README.md).

- [Grace Canvas Eval](benchmarks/grace_canvas_eval/README.md) evaluates structured
  canvas drawing actions against Grace's canvas task set.
- [Grace Chatbot Eval](benchmarks/grace_chatbot_eval/README.md) compares blind,
  multi-turn conversations for warmth, coherence, and persona fit.

## Running Grace Canvas Eval

Grace Canvas Eval imports the canvas engine and image kinds from an AGi source
checkout. Set `AGI_REPO` to that checkout's path when running the harness:

```bash
AGI_REPO=/path/to/AGi python benchmarks/grace_canvas_eval/grace_canvas_eval.py \
    --base-url http://127.0.0.1:8080/v1 \
    --model ministral-3-14b-instruct-2512 \
    --label ministral3-14b \
    --out results/ministral.json \
    --out-dir renders/ministral
```

Install its one-off Python dependencies and model-serving requirements from
the [Grace Canvas Eval guide](benchmarks/grace_canvas_eval/README.md).
