# Inference performance

Compare a running llama.cpp or RustingStrata server through its OpenAI-compatible
streaming API. The runner uses Python's standard library; local resource sampling
uses Linux `/proc`, `ss` for PID discovery, and optional `nvidia-smi`.

From the AGi root, with the local Ministral server running:

```bash
./AIVA/scorecard.sh perf \
  --base-url http://127.0.0.1:8080/v1 \
  --model ministral-3-8b-instruct-2512-abliterated \
  --backend llama.cpp-b12766 \
  --label ministral-iq4-perf
```

Defaults: approximately 512, 2048, and 8192 user-content tokens, 256 maximum output
tokens, temperature 0, one full warmup per length, and three measured repetitions.
The tokenizer endpoint sizes the input; API usage reports the actual prompt count
including the chat template. Each request starts with a fresh identifier to prevent
prefix reuse, and sends `cache_prompt=false`. Cached-token counts are recorded
because backend behavior can differ. There is no system/persona prompt.

To use RustingStrata, point the same command at its endpoint and supply its exact
model ID (`curl -s http://127.0.0.1:8081/v1/models` lists IDs):

```bash
./AIVA/scorecard.sh perf \
  --base-url http://127.0.0.1:8081/v1 \
  --model YOUR_STRATA_MODEL_ID \
  --backend RustingStrata-1.3.7 \
  --model-file /path/to/model.gguf \
  --label inkling-strata-perf
```

The runner uses existing server processes. It does not start, stop, reload, or
reconfigure a server. A request can trigger the server's own automatic model load.
It does not change AIVA's router preset. Test models/backends sequentially, using
the same GPU placement, context capacity, KV types, output length, and reasoning
configuration. Keep the machine otherwise idle when making speed comparisons.
The current local UD Ministral file is the original instruct model while the `i1`
files are abliterated: that also changes the base weights, not only the quantizer.

## Measurements

| Metric | Meaning |
|---|---|
| TTFT | Request start to first nonempty content, reasoning, or tool-call chunk, including HTTP, queueing, prefill and first decode work. Blank chunks, role deltas, and heartbeat comments do not count. |
| First answer | Request start to first nonempty visible content; reasoning can make this much later than TTFT. |
| Prefill / decode (server) | Server's `timings.prompt_per_second` and `predicted_per_second`, or corresponding counts divided by durations. Uncached prompt counts are used by those timing fields. |
| Prefill estimate | Uncached prompt tokens divided by TTFT. This includes transport, queueing and first decode; it is not a direct measurement of prefill. Available in JSON/CSV when cache counts are known. |
| Decode estimate | `(completion_tokens - 1) / (last_output_time - first_output_time)`. Assumes one token in the first output chunk. Multi-token speculative bursts and output buffering make this approximate; the table labels it separately. |
| End-to-end tok/s | Total generated tokens divided by full HTTP request time, including prefill. Reasoning tokens count as generated work when included in server usage. |
| Chunk gap p95 | 95th percentile of intervals between nonempty output chunks. Chunks may contain several tokens, so this is not per-token latency. |
| Latency | Request start through the finish-reason event. Raw records also contain full HTTP time. |
| RAM RSS / PSS | Peak sampled resident/proportional memory of the selected server PID tree, in MiB. PSS avoids double counting shared pages between workers. Mapped model pages count; unused virtual mappings do not. Swap is recorded separately. |
| VRAM | Peak sampled GPU allocation attributed to the selected server PIDs, both total and per GPU. Device-wide used memory, minimum free memory, peak utilization, power and temperature are also recorded, including other GPU clients. |
| File size | Exact bytes and GiB for each supplied/discovered GGUF, with SHA-256. Repeat `--model-file` to include draft/projector files; the combined size appears in comparisons. |

Timings are taken from streamed final chunks when the backend provides them. Some
RustingStrata model paths (including the inspected Inkling path) report usage but
omit `timings`: server rates then remain unavailable, with TTFT and labeled client
estimates still available. No token counts are guessed from character counts.
Early EOS is allowed: actual generated length and finish reason are recorded.
This measures experienced streaming performance, including speculation when the
running server enables it. It does not measure unassisted kernel throughput or
cold process-start/load time. Warmups may incur model loading and are excluded.

The report includes median, mean, standard deviation and p95 over repetitions;
three samples give a useful initial comparison but a weak tail-latency estimate.
Use `--repeats 5` or higher for more stable results. Memory peaks are sampled at
0.5-second intervals and can miss brief spikes. They describe the running server's
actual allocation policy, not a prediction for a different configured context.

## Resources and artifacts

For loopback URLs the runner discovers the listening process. With llama.cpp's
router it prefers the worker matching the model's `--alias`, excluding unrelated
resident models. Inspect `manifest.json` for the selected PIDs. Pass
`--pid WORKER_PID` explicitly to isolate a model, or pass the router PID to measure
the whole service and its children. Repeat `--pid` to monitor multiple roots.
For a remote endpoint, RAM/VRAM cannot be measured from this client: run this tool
on the server host for those metrics. A forwarded port's proxy PID is not the
remote inference process; use the server host instead. NVIDIA metrics are optional
and appear as unavailable on unsupported systems.

File paths are discovered from the local model worker arguments when possible;
otherwise supply `--model-file`. This records the files on disk and does not prove
that a running process loaded the same bytes if files were replaced after startup.
Hashing reads the files and warms the OS file cache. It happens before measurement.

Results are saved under `diagnostic/scorecard/results/inference_perf/LABEL/`
(ignored by Git). Existing labels/directories are refused, never overwritten.

- `manifest.json`: endpoint/model, generation options, local server command lines,
  model metadata, files/checksums, machine, and pre-run resources. The API key is
  read from `OPENAI_API_KEY` (or `--api-key-env NAME`) and is not stored.
- `requests.jsonl`: input and measured metrics for each request, including warmups,
  errors, cached tokens, raw timing fields, and sampled memory peaks.
- `response-*.json`: streamed events with arrival times and generated output.
- `resources-*.jsonl`: resource sample series for each request.
- `summary.json`, `summary.csv`, `summary.md`: per-length comparison data. Warmups
  and failed requests are excluded from speed summaries; failures are counted.
  Summaries update after each request, including interruptions.

To compare saved runs:

```bash
./AIVA/scorecard.sh perf compare \
  diagnostic/scorecard/results/inference_perf/ministral-iq4-perf \
  diagnostic/scorecard/results/inference_perf/ministral-q4km-perf
```

Switch the model yourself, rerun with the corresponding model ID and a new label,
then compare. The comparison reads files only and does not send inference requests.
It flags differing generation options; inspect manifests for server context/KV,
hardware and speculation differences, too.

## Useful options

```bash
# Short integration smoke check (not a stable speed result)
./AIVA/scorecard.sh perf --model YOUR_MODEL_ID --label perf-smoke \
  --prompt-tokens 128 --output-tokens 16 --warmup 0 --repeats 1

# Longer contexts / more repetitions (must fit the running server's context)
./AIVA/scorecard.sh perf --model YOUR_MODEL_ID --label perf-long \
  --prompt-tokens 512 4096 12000 --output-tokens 256 --repeats 5

# Explicit thinking control: otherwise the server/model defaults are preserved
./AIVA/scorecard.sh perf --model YOUR_MODEL_ID --label perf-low \
  --reasoning-effort low --extra-body '{"reasoning_budget":2048}'
./AIVA/scorecard.sh perf --model YOUR_MODEL_ID --label perf-no-think --think-off
```

`--extra-body` forwards additional generation options unchanged. Support for
reasoning/budget options is backend-specific; this tool does not translate them.
`--sample-interval 0.25` increases resource sampling frequency with more overhead.
`--no-gpu` disables NVIDIA polling. `--help` lists all options.

Run the focused protocol/telemetry tests from the AGi root:

```bash
python3 -m unittest discover -s diagnostic/scorecard/benchmarks/inference_perf -p 'test_*.py' -v
```
