#!/usr/bin/env python3
"""Stream OpenAI-compatible chats and sample a local server's RAM/NVIDIA VRAM.

Uses the Python standard library, /proc, and optional nvidia-smi. Does not manage
server processes. See README.md for metric definitions and comparison protocol.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone


RESULTS = Path(__file__).resolve().parents[2] / "results" / "inference_perf"
CORPUS = (
    "Reliable software grows through small changes, clear interfaces, and careful observation. "
    "A useful plan identifies assumptions, checks the result, and leaves room for revision. "
    "Community gardens depend on local soil, seasonal weather, shared tools, and regular care. "
    "Travel planning balances walking distance, public transport, accessibility, and time to rest. "
    "Preparing a meal involves choosing ingredients, organizing equipment, and controlling heat. "
    "A research notebook separates measurements from predictions and records unexpected findings. "
    "Learning a language combines listening, reading, practice, feedback, and patient repetition. "
    "Designing a home workspace requires comfortable lighting, useful storage, and quiet surroundings. "
    "A budget connects current resources with future goals while allowing for uncertain expenses. "
    "Teams solve problems by sharing evidence, testing alternatives, and documenting decisions. "
).split()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def run_text(command):
    return subprocess.run(command, capture_output=True, text=True, timeout=5, check=True).stdout


class API:
    def __init__(self, base_url, key, timeout):
        self.base = base_url.rstrip("/")
        self.origin = self.base[:-3] if self.base.endswith("/v1") else self.base
        self.headers = {"Content-Type": "application/json"}
        if key:
            self.headers["Authorization"] = "Bearer " + key
        self.timeout = timeout

    def open(self, url, body=None):
        request = urllib.request.Request(url, headers=self.headers,
                                         data=None if body is None else json.dumps(body).encode())
        try:
            return urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.read(4096).decode(errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc

    def get(self, path):
        with self.open(self.base + path) as response:
            return json.load(response)

    def token_count(self, model, content):
        with self.open(self.origin + "/tokenize", {"model": model, "content": content,
                                                  "add_special": False}) as response:
            return len(json.load(response)["tokens"])


def stream_events(response):
    """Parse SSE frames, including comments, blank heartbeats and multiline data."""
    lines = []
    for raw in response:
        line = raw.decode("utf-8").rstrip("\r\n")
        if not line:
            if lines:
                yield "\n".join(lines)
                lines = []
        elif line.startswith("data:"):
            lines.append(line[5:].lstrip(" "))
    if lines:
        yield "\n".join(lines)


def streamed_chat(api, body):
    start = time.perf_counter()
    first_output = first_answer = last_output = finished = None
    usage, timings, finish_reason = {}, {}, None
    text, reasoning, events, gaps = [], [], [], []
    done = False
    with api.open(api.base + "/chat/completions", body) as response:
        if "text/event-stream" not in response.headers.get("Content-Type", ""):
            raise ValueError("Endpoint did not return an SSE stream")
        for data in stream_events(response):
            now = time.perf_counter()
            if data == "[DONE]":
                done = True
                break
            event = json.loads(data)
            if event.get("error"):
                raise RuntimeError(str(event["error"]))
            events.append({"elapsed_s": now - start, "data": event})
            if event.get("usage"):
                usage.update(event["usage"])
            if event.get("timings"):
                timings.update(event["timings"])
            for choice in event.get("choices", []):
                delta = choice.get("delta") or {}
                answer = delta.get("content") or ""
                thought = delta.get("reasoning_content") or delta.get("reasoning") or ""
                output = bool(answer or thought or delta.get("tool_calls"))
                if output:
                    if first_output is None:
                        first_output = now
                    if last_output is not None:
                        gaps.append((now - last_output) * 1000)
                    last_output = now
                if answer and first_answer is None:
                    first_answer = now
                text.append(answer)
                reasoning.append(thought)
                if choice.get("finish_reason") is not None:
                    finish_reason = choice["finish_reason"]
                    finished = now
    end = time.perf_counter()
    if not done or finish_reason is None:
        raise ValueError("Incomplete stream: missing [DONE] or finish_reason")
    if first_output is None:
        raise ValueError("No content, reasoning, or tool-call output received")
    prompt_n = usage.get("prompt_tokens")
    completion_n = usage.get("completion_tokens", timings.get("predicted_n"))
    cached_n = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", timings.get("cache_n"))
    uncached_n = timings.get("prompt_n")
    if uncached_n is None and prompt_n is not None and cached_n is not None:
        uncached_n = max(0, prompt_n - cached_n)
    prefill = positive_rate(timings, "prompt_per_second", "prompt_n", "prompt_ms")
    decode = positive_rate(timings, "predicted_per_second", "predicted_n", "predicted_ms")
    ttft = first_output - start
    output_interval = last_output - first_output
    # This approximation assumes the first text chunk contains one output token.
    # Keep it separate: speculative decoders can send many tokens per chunk.
    decode_estimate = ((completion_n - 1) / output_interval
                       if completion_n and completion_n > 1 and output_interval > 0 else None)
    return {
        "ttft_ms": ttft * 1000,
        "first_answer_ms": (first_answer - start) * 1000 if first_answer else None,
        "latency_ms": ((finished or end) - start) * 1000,
        "http_total_ms": (end - start) * 1000,
        "prompt_tokens": prompt_n, "completion_tokens": completion_n,
        "cached_tokens": cached_n, "uncached_prompt_tokens": uncached_n,
        "server_prefill_tps": prefill, "server_decode_tps": decode,
        "prefill_estimate_tps": uncached_n / ttft if uncached_n and ttft > 0 else None,
        "decode_estimate_tps": decode_estimate,
        "end_to_end_tps": completion_n / (end - start) if completion_n else None,
        "chunk_gap_p95_ms": percentile(gaps, .95),
        "finish_reason": finish_reason, "usage": usage, "timings": timings,
        "text": "".join(text), "reasoning": "".join(reasoning), "events": events,
    }


def positive_rate(timings, rate, count, duration):
    value = timings.get(rate)
    if isinstance(value, (int, float)) and value > 0 and math.isfinite(value):
        return value
    n, ms = timings.get(count), timings.get(duration)
    return n * 1000 / ms if n and ms and n > 0 and ms > 0 else None


def percentile(values, quantile):
    if not values:
        return None
    values = sorted(values)
    pos = (len(values) - 1) * quantile
    lower = int(pos)
    return values[lower] + (values[min(lower + 1, len(values) - 1)] - values[lower]) * (pos - lower)


def prompt_text(words, nonce):
    source = " ".join(CORPUS[i % len(CORPUS)] for i in range(words))
    return (f"Request {nonce}. Read these notes:\n{source}\n\n"
            "Write an extensive practical essay connecting the ideas in the notes. "
            "Include concrete examples and explain tradeoffs. Continue with useful detail.")


def size_prompt(api, model, target):
    """Target user-content tokens; the chat template adds its own overhead."""
    nonce = "0" * 32
    words = max(1, int(target * .7))
    try:
        for attempt in range(5):
            count = api.token_count(model, prompt_text(words, nonce))
            if abs(count - target) <= max(4, target * .01):
                break
            if words == 1 and count > target:
                break
            if attempt == 4:
                break
            words = max(1, int(words * target / max(count, 1)))
        return words, "tokenize", count
    except (OSError, RuntimeError, ValueError, KeyError):
        return words, "approximate_without_tokenizer", None


def process_tree(roots):
    """Follow router workers too. PSS accounts for pages shared between workers."""
    parents = {}
    for entry in Path("/proc").glob("[0-9]*/stat"):
        try:
            fields = entry.read_text().rsplit(")", 1)[1].split()
            parents[int(entry.parent.name)] = int(fields[1])
        except (OSError, ValueError, IndexError):
            pass
    selected = set(roots) & parents.keys()
    while True:
        more = {pid for pid, parent in parents.items() if parent in selected}
        if more <= selected:
            return selected
        selected.update(more)


def process_memory(pids):
    rss = pss = swap = 0
    readable = 0
    for pid in pids:
        try:
            values = dict(re.findall(r"^(Rss|Pss|Swap):\s+(\d+)",
                                     Path(f"/proc/{pid}/smaps_rollup").read_text(), re.M))
            rss += int(values["Rss"]) / 1024
            pss += int(values["Pss"]) / 1024
            swap += int(values["Swap"]) / 1024
            readable += 1
        except (OSError, KeyError):
            pass
    return {"rss_mib": rss if readable else None, "pss_mib": pss if readable else None,
            "swap_mib": swap if readable else None, "memory_pids_read": readable}


def nvidia_snapshot(pids):
    fields = ["uuid", "index", "name", "memory.total", "memory.used", "utilization.gpu",
              "power.draw", "temperature.gpu"]
    cards = {}
    for row in csv.reader(run_text(["nvidia-smi", "--query-gpu=" + ",".join(fields),
                                    "--format=csv,noheader,nounits"]).splitlines()):
        key, index, name, *numbers = [x.strip() for x in row]
        vals = [float(x) if re.fullmatch(r"[\d.]+", x) else None for x in numbers]
        cards[key] = dict(zip(["total_mib", "used_mib", "utilization_pct", "power_w", "temperature_c"], vals))
        cards[key].update(index=int(index), name=name, process_mib=0.0 if pids else None)
    rows = run_text(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,used_gpu_memory",
                     "--format=csv,noheader,nounits"])
    for row in csv.reader(rows.splitlines()):
        if len(row) != 3:
            continue
        key, pid, mem = [x.strip() for x in row]
        if key in cards and pid.isdigit() and int(pid) in pids:
            if re.fullmatch(r"[\d.]+", mem):
                cards[key]["process_mib"] += float(mem)
            else:
                cards[key]["process_mib"] = None
    return cards


class Monitor:
    def __init__(self, roots, interval, gpu):
        self.roots, self.interval, self.gpu = roots, interval, gpu
        self.notes = set()
        self.stop = threading.Event()

    def snapshot(self):
        pids = process_tree(self.roots) if self.roots else set()
        row = {"at": utc_now(), "pids": sorted(pids), **process_memory(pids)}
        try:
            info = dict(re.findall(r"^(MemTotal|MemAvailable|SwapTotal|SwapFree):\s+(\d+)",
                                   Path("/proc/meminfo").read_text(), re.M))
            row["system_available_mib"] = int(info["MemAvailable"]) / 1024
            row["system_swap_used_mib"] = (int(info["SwapTotal"]) - int(info["SwapFree"])) / 1024
        except (OSError, KeyError):
            pass
        if self.gpu:
            try:
                row["gpus"] = nvidia_snapshot(pids)
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                self.notes.add(f"NVIDIA sampling unavailable: {type(exc).__name__}")
        if self.roots and (not pids or row["memory_pids_read"] < len(pids)):
            self.notes.add("Some server processes disappeared or denied RAM accounting; check sample PID lists.")
        return row

    def start(self, path):
        self.samples = []
        self.stop.clear()
        def collect():
            with path.open("w") as file:
                while True:
                    start = time.monotonic()
                    sample = self.snapshot()
                    self.samples.append(sample)
                    file.write(json.dumps(sample) + "\n")
                    file.flush()
                    if self.stop.wait(max(0, self.interval - (time.monotonic() - start))):
                        break
        self.thread = threading.Thread(target=collect, daemon=True)
        self.thread.start()

    def finish(self):
        self.stop.set()
        self.thread.join()
        self.samples.append(self.snapshot())
        return resource_peaks(self.samples)


def resource_peaks(samples):
    def maximum(field):
        return max((s[field] for s in samples if s.get(field) is not None), default=None)
    gpus = {}
    for sample in samples:
        for key, card in sample.get("gpus", {}).items():
            out = gpus.setdefault(key, {"index": card["index"], "name": card["name"],
                                        "total_mib": card["total_mib"]})
            for field in ("process_mib", "used_mib", "utilization_pct", "power_w", "temperature_c"):
                if card.get(field) is not None:
                    out[field + "_peak"] = max(out.get(field + "_peak", 0), card[field])
    for card in gpus.values():
        used = card.get("used_mib_peak")
        card["free_mib_min"] = card["total_mib"] - used if used is not None else None
    # Sum cards within each timestamp; don't add unrelated per-card maxima.
    totals = [sum(c["process_mib"] for c in s["gpus"].values()) for s in samples
              if s.get("gpus") and all(c.get("process_mib") is not None for c in s["gpus"].values())]
    return {"rss_mib_peak": maximum("rss_mib"), "pss_mib_peak": maximum("pss_mib"),
            "swap_mib_peak": maximum("swap_mib"), "gpus": gpus,
            "vram_mib_peak": max(totals, default=None), "samples": len(samples)}


def discover_pids(base_url):
    url = urllib.parse.urlsplit(base_url)
    if url.hostname not in ("localhost", "127.0.0.1", "::1"):
        return []
    try:
        out = run_text(["ss", "-H", "-ltnp", f"sport = :{url.port or (443 if url.scheme == 'https' else 80)}"])
        return sorted({int(pid) for pid in re.findall(r"pid=(\d+)", out)})
    except (OSError, subprocess.SubprocessError):
        return []


def process_metadata(pids):
    records = []
    for pid in sorted(process_tree(pids)):
        try:
            args = Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace").split("\0")
            redact_next = False
            safe = []
            for arg in filter(None, args):
                if redact_next:
                    safe.append("<redacted>")
                    redact_next = False
                elif re.search(r"(?:api[-_]?key|token|password|secret)", arg.split("=", 1)[0], re.I):
                    if "=" in arg:
                        safe.append(arg.split("=", 1)[0] + "=<redacted>")
                    else:
                        safe.append(arg)
                        redact_next = True
                else:
                    safe.append(arg)
            records.append({"pid": pid, "executable": os.readlink(f"/proc/{pid}/exe"), "argv": safe})
        except OSError:
            pass
    return records


def target_workers(pids, model):
    """Prefer a llama.cpp router's named worker to unrelated resident models."""
    matches = []
    for process in process_metadata(pids):
        argv = process["argv"]
        if "--alias" in argv:
            aliases = argv[argv.index("--alias") + 1].split(",")
            if model in aliases:
                matches.append(process["pid"])
    return matches or pids


def discover_model_files(model_info, processes):
    argv = (model_info.get("status") or {}).get("args") or []
    candidates = [argv] if argv else [p["argv"] for p in processes]
    paths = []
    for args in candidates:
        for i, arg in enumerate(args[:-1]):
            if arg in ("--model", "-m", "--model-draft", "-md", "--mmproj"):
                path = Path(args[i + 1]).expanduser()
                if path.is_file() and path not in paths:
                    paths.append(path)
    return paths


def discover_model_files(model_info, processes):
    argv = (model_info.get("status") or {}).get("args", [])
    if not argv and len(processes) == 1:
        argv = processes[0]["argv"]
    paths = []
    for flag in ("--model", "-m", "--model-draft", "-md"):
        if flag in argv and argv.index(flag) + 1 < len(argv):
            path = Path(argv[argv.index(flag) + 1]).expanduser()
            if path.is_file() and path not in paths:
                paths.append(path)
    return paths


def model_metadata(paths):
    records = []
    for path in paths:
        path = path.expanduser().resolve(strict=True)
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for block in iter(lambda: file.read(8 * 1024 * 1024), b""):
                digest.update(block)
        records.append({"path": str(path), "bytes": path.stat().st_size, "sha256": digest.hexdigest()})
    return records


METRICS = ("ttft_ms", "first_answer_ms", "latency_ms", "server_prefill_tps", "server_decode_tps",
           "prefill_estimate_tps", "decode_estimate_tps", "end_to_end_tps", "chunk_gap_p95_ms",
           "prompt_tokens", "completion_tokens", "cached_tokens")


def summarize(records):
    groups = []
    for target in sorted({r["target_prompt_tokens"] for r in records if not r["warmup"]}):
        rows = [r for r in records if r["target_prompt_tokens"] == target and not r["warmup"]]
        good = [r for r in rows if r["status"] == "ok"]
        group = {"target_prompt_tokens": target, "successful": len(good), "failed": len(rows) - len(good)}
        for key in METRICS:
            values = [r[key] for r in good if r.get(key) is not None]
            group[key] = {"n": len(values), "mean": statistics.mean(values) if values else None,
                          "median": statistics.median(values) if values else None,
                          "p95": percentile(values, .95),
                          "stddev": statistics.stdev(values) if len(values) > 1 else None}
        resources = [r["resources"] for r in good]
        for key in ("rss_mib_peak", "pss_mib_peak", "vram_mib_peak", "swap_mib_peak"):
            group[key] = max((r[key] for r in resources if r.get(key) is not None), default=None)
        group["gpus"] = resource_peaks([{"gpus": {k: {
            "index": v["index"], "name": v["name"], "total_mib": v["total_mib"],
            **{key: v.get(key + "_peak") for key in ("process_mib", "used_mib", "utilization_pct", "power_w", "temperature_c")}
        } for k, v in r.get("gpus", {}).items()}} for r in resources])["gpus"]
        groups.append(group)
    return groups


def fmt(value):
    return "—" if value is None else f"{value:,.1f}"


def render_table(summary, comparison=False):
    prefix = "| Run | Files GiB " if comparison else ""
    header = "| Target prompt | Actual prompt | OK/fail | TTFT ms | Prefill tok/s (server) | Prefill est. tok/s | Decode tok/s (server) | Decode est. tok/s | Latency ms | RAM PSS MiB | VRAM MiB | GPU VRAM MiB |"
    lines = [prefix + header if comparison else header,
             "|" + "---:|" * (14 if comparison else 12)]
    for group in summary:
        values = [str(group["target_prompt_tokens"]), fmt(group["prompt_tokens"]["median"]), f'{group["successful"]}/{group["failed"]}']
        values += [fmt(group[k]["median"]) for k in ("ttft_ms", "server_prefill_tps", "prefill_estimate_tps", "server_decode_tps", "decode_estimate_tps", "latency_ms")]
        values += [fmt(group[k]) for k in ("pss_mib_peak", "vram_mib_peak")]
        values.append(", ".join(f'GPU{g["index"]}: {fmt(g.get("process_mib_peak"))}'
                                for g in sorted(group["gpus"].values(), key=lambda g: g["index"])) or "—")
        if comparison:
            values = [group["label"], fmt(group.get("file_bytes") / 2**30) if group.get("file_bytes") is not None else "—"] + values
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def save_summary(output, manifest, records, notes):
    groups = summarize(records)
    report = {"label": manifest["label"], "backend": manifest["backend"], "model": manifest["model"],
              "finished_at": utc_now(), "groups": groups, "notes": sorted(notes),
              "model_files": manifest["model_files"], "generation": manifest["generation"],
              "file_bytes": sum(f["bytes"] for f in manifest["model_files"]) if manifest["model_files"] else None}
    write_json(output / "summary.json", report)
    with (output / "summary.csv").open("w", newline="") as file:
        rows = []
        for group in groups:
            row = {k: v for k, v in group.items() if not isinstance(v, dict)}
            row.update(label=manifest["label"], backend=manifest["backend"], model=manifest["model"], file_bytes=report["file_bytes"])
            for key in METRICS:
                row.update({f"{key}_{stat}": value for stat, value in group[key].items()})
            for card in group["gpus"].values():
                row.update({f'gpu{card["index"]}_{key}': value for key, value in card.items()
                            if key not in ("index", "name")})
            rows.append(row)
        fields = list(dict.fromkeys(key for row in rows for key in row))
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    table = render_table(groups)
    files = "\n".join(f'- {Path(f["path"]).name}: {f["bytes"]:,} bytes ({f["bytes"] / 2**30:.3f} GiB); SHA-256 `{f["sha256"]}`'
                      for f in manifest["model_files"])
    (output / "summary.md").write_text(f'# {manifest["label"]}\n\n{files or "File size unavailable; supply --model-file."}\n\n{table}\n\n'
        "Speeds/latencies shown are medians; memory values are sampled peaks. "
        "A dash means unavailable. See manifest.json and requests.jsonl for settings and individual results.\n")
    return table


def compare_results(argv):
    parser = argparse.ArgumentParser(description="Compare saved inference performance runs")
    parser.add_argument("runs", type=Path, nargs="+", help="Run directories or summary.json files")
    args = parser.parse_args(argv)
    groups, settings = [], []
    for path in args.runs:
        report = json.loads((path / "summary.json" if path.is_dir() else path).read_text())
        groups += [{**g, "label": report["label"], "file_bytes": report.get("file_bytes")} for g in report["groups"]]
        settings.append({"label": report["label"], "generation": report.get("generation")})
        print(f'{report["label"]}: {report["backend"]}, model={report["model"]}')
    print("\n" + render_table(groups, comparison=True))
    if any(s["generation"] != settings[0]["generation"] for s in settings[1:]):
        print("\nGeneration settings differ between these runs; check each manifest.json.")
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/v1")
    parser.add_argument("--model", required=True, help="Exact /v1/models ID")
    parser.add_argument("--label", required=True, help="New result label; existing results are never overwritten")
    parser.add_argument("--backend", default="unspecified", help="Recorded backend/version, e.g. llama.cpp-b12766")
    parser.add_argument("--pid", type=int, action="append", help="Local server PID, repeatable; includes descendants. Auto-detected for loopback endpoints")
    parser.add_argument("--model-file", type=Path, action="append", default=[], help="Optional local weight/draft file to SHA-256; repeatable")
    parser.add_argument("--prompt-tokens", type=int, nargs="+", default=[512, 2048, 8192], help="Approximate user-content lengths; actual templated counts come from usage")
    parser.add_argument("--output-tokens", type=int, default=256)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=1, help="Full warmup requests per length; excluded from speed summaries")
    parser.add_argument("--think-off", action="store_true", help="Send enable_thinking=false; otherwise preserve model/server default")
    parser.add_argument("--reasoning-effort", help="Forward reasoning_effort unchanged")
    parser.add_argument("--extra-body", default="{}", help="Additional generation options as a JSON object; stored with results")
    parser.add_argument("--sample-interval", type=float, default=.5)
    parser.add_argument("--no-gpu", action="store_true", help="Disable local NVIDIA telemetry")
    parser.add_argument("--timeout", type=float, default=600, help="HTTP socket timeout seconds")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY", help="Environment variable containing optional API key; key is never saved")
    parser.add_argument("--output-dir", type=Path, help="New output directory; default scorecard/results/inference_perf/<label>")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", args.label):
        parser.error("--label must use letters, digits, underscores, dots or hyphens")
    if min(args.prompt_tokens + [args.output_tokens, args.repeats]) <= 0 or args.warmup < 0:
        parser.error("Token counts and repeats must be positive; warmup must be >= 0")
    if args.sample_interval < .1 or args.timeout <= 0:
        parser.error("--sample-interval must be >= 0.1 and --timeout must be positive")
    url = urllib.parse.urlsplit(args.base_url)
    if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment:
        parser.error("Use an http(s) base URL without credentials, query, or fragment")
    try:
        args.extra_body = json.loads(args.extra_body)
    except ValueError:
        parser.error("--extra-body must be JSON")
    if not isinstance(args.extra_body, dict):
        parser.error("--extra-body must be an object")
    reserved = {"model", "messages", "stream", "stream_options", "max_tokens", "max_completion_tokens", "n"}
    if reserved & args.extra_body.keys():
        parser.error("--extra-body cannot replace model/messages/stream/output-token settings")
    if "chat_template_kwargs" in args.extra_body and not isinstance(args.extra_body["chat_template_kwargs"], dict):
        parser.error("chat_template_kwargs must be an object")
    if args.pid and min(args.pid) <= 0:
        parser.error("--pid must be positive")
    return args


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "compare":
        return compare_results(argv[1:])
    args = parse_args(argv)
    output = (args.output_dir or RESULTS / args.label).expanduser().resolve()
    if output.exists():
        raise ValueError(f"Output already exists: {output}. Use a new label/directory.")
    api = API(args.base_url, os.environ.get(args.api_key_env, ""), args.timeout)
    models = api.get("/models")
    ids = [m["id"] for m in models.get("data", [])]
    if args.model not in ids:
        raise ValueError(f"Unknown model {args.model!r}. Server advertises: {ids}")
    model_info = next(m for m in models["data"] if m["id"] == args.model)
    pids = args.pid if args.pid is not None else discover_pids(args.base_url)
    if args.pid is None:
        pids = target_workers(pids, args.model)
    if args.pid and any(not Path(f"/proc/{pid}").exists() for pid in pids):
        raise ValueError("A supplied server PID is not running")
    local = urllib.parse.urlsplit(args.base_url).hostname in ("localhost", "127.0.0.1", "::1")
    gpu = not args.no_gpu and bool(shutil.which("nvidia-smi")) and (local or bool(pids))
    monitor = Monitor(pids, args.sample_interval, gpu)
    notes = set()
    if not pids:
        notes.add("Server RAM and process VRAM unavailable: no local server PID. Remote resources require running this tool on that server.")
    if pids and args.pid is None:
        notes.add("Auto-detected server socket and named model worker; inspect manifest.json for resource scope.")
    print(f"{args.label}: {args.model} on {args.base_url}", flush=True)
    print(f"Resource scope: PIDs {pids or 'unavailable'}, NVIDIA telemetry {'on' if gpu else 'off'}", flush=True)
    processes = process_metadata(pids)
    paths = args.model_file or (discover_model_files(model_info, processes) if pids else [])
    if paths:
        print("Hashing model artifacts…", flush=True)
    files = model_metadata(paths)
    for file in files:
        print(f'  {Path(file["path"]).name}: {file["bytes"]:,} bytes ({file["bytes"] / 2**30:.3f} GiB)', flush=True)
    generation = {"temperature": 0, "max_tokens": args.output_tokens, "stream": True,
                  "stream_options": {"include_usage": True}, "cache_prompt": False, **args.extra_body}
    if args.think_off:
        kwargs = generation.setdefault("chat_template_kwargs", {})
        kwargs["enable_thinking"] = False
    if args.reasoning_effort:
        generation["reasoning_effort"] = args.reasoning_effort
    manifest = {"schema_version": 1, "created_at": utc_now(), "label": args.label,
        "backend": args.backend, "model": args.model, "base_url": args.base_url,
        "generation": generation, "prompt_targets": args.prompt_tokens, "repeats": args.repeats,
        "warmup_per_length": args.warmup, "sample_interval_s": args.sample_interval,
        "server_roots": pids, "server_processes_before": processes,
        "model_files": files, "host": {"hostname": platform.node(), "platform": platform.platform(),
                                       "cpu_count": os.cpu_count()},
        "server_model_info": {k: model_info[k] for k in ("id", "meta", "context_length", "memory", "architecture") if k in model_info},
        "resources_before": monitor.snapshot()}
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "manifest.json", manifest)
    records = []
    interrupted = False
    try:
        with (output / "requests.jsonl").open("a") as file:
            for target in args.prompt_tokens:
                words, sizing, count = size_prompt(api, args.model, target)
                if sizing != "tokenize":
                    notes.add("Tokenizer endpoint unavailable for some workloads; prompt sizes are approximate. Check actual prompt_tokens.")
                for iteration in range(args.warmup + args.repeats):
                    warmup = iteration < args.warmup
                    run_id = f"p{target}-{iteration}-{uuid.uuid4().hex[:8]}"
                    body = {"model": args.model, **generation, "messages": [{"role": "user",
                            "content": prompt_text(words, uuid.uuid4().hex)}]}
                    record = {"id": run_id, "at": utc_now(), "target_prompt_tokens": target,
                              "warmup": warmup, "iteration": iteration, "prompt_sizing": sizing,
                              "sizing_token_count": count, "request": body}
                    stage = "warmup" if warmup else f"run {iteration - args.warmup + 1}/{args.repeats}"
                    print(f"  ~{target} prompt tokens, {stage}…", flush=True)
                    monitor.start(output / f"resources-{run_id}.jsonl")
                    try:
                        result = streamed_chat(api, body)
                        write_json(output / f"response-{run_id}.json", result)
                        record.update({k: v for k, v in result.items() if k not in ("text", "reasoning", "events")})
                        record["status"] = "ok"
                        if record["completion_tokens"] is None:
                            notes.add("Some responses omitted token counts; token rates unavailable for those requests.")
                        if record["cached_tokens"] is None:
                            notes.add("Some responses omitted cached-token counts; cache reuse cannot be verified for those requests.")
                        elif record["cached_tokens"] > 32:
                            notes.add("Some prompts reused >32 cached tokens despite fresh prefixes. Compare uncached prompt counts before interpreting prefill speeds.")
                    except KeyboardInterrupt:
                        record.update(status="interrupted", error="KeyboardInterrupt")
                        raise
                    except Exception as exc:
                        record.update(status="error", error=f"{type(exc).__name__}: {exc}")
                        print(f'    ERROR: {record["error"]}', flush=True)
                    finally:
                        record["resources"] = monitor.finish()
                        records.append(record)
                        file.write(json.dumps(record, allow_nan=False) + "\n")
                        file.flush()
                        save_summary(output, manifest, records, notes | monitor.notes)
                    if record["status"] == "ok":
                        print(f'    TTFT {fmt(record["ttft_ms"])} ms | prefill {fmt(record["server_prefill_tps"])} '
                              f'| decode {fmt(record["server_decode_tps"])} tok/s | '
                              f'{record["completion_tokens"]} output tokens', flush=True)
    except KeyboardInterrupt:
        interrupted = True
    finally:
        manifest["server_processes_after"] = process_metadata(pids)
        manifest["resources_after"] = monitor.snapshot()
        write_json(output / "manifest.json", manifest)
        table = save_summary(output, manifest, records, notes | monitor.notes)
        print("\n" + table + f"\n\nResults: {output}", flush=True)
    return 130 if interrupted else int(any(r["status"] != "ok" for r in records))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
