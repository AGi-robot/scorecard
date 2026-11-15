# Scorecard

Shared model benchmark suites for AGi projects.

## Benchmarks

- [CanvasBench for Grace](benchmarks/canvas/README.md) evaluates structured
  canvas drawing actions against Grace's canvas task set.

## Running CanvasBench

CanvasBench imports the canvas engine and image kinds from an AGi source
checkout. Set `AGI_REPO` to that checkout's path when running the harness:

```bash
AGI_REPO=/path/to/AGi python benchmarks/canvas/canvas_bench.py \
    --base-url http://127.0.0.1:8080/v1 \
    --model ministral-3-14b-instruct-2512 \
    --label ministral3-14b \
    --out results/ministral.json \
    --out-dir renders/ministral
```

Install its one-off Python dependencies and model-serving requirements from
the [CanvasBench guide](benchmarks/canvas/README.md).
