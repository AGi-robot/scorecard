"""Protocol/attribution tests; synthetic data here is never a model benchmark."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import inference_perf as perf


def sse(events, done=True):
    data = b": heartbeat\n\n" + b"".join(
        b"data: " + json.dumps(event).encode() + b"\n\n" for event in events)
    return data + (b"data: [DONE]\n\n" if done else b"")


class Response(io.BytesIO):
    headers = {"Content-Type": "text/event-stream"}


class FakeAPI:
    base = "http://example.invalid/v1"

    def __init__(self, events, done=True):
        self.events, self.done = events, done

    def open(self, url, body):
        return Response(sse(self.events, self.done))


class StreamTests(unittest.TestCase):
    def test_llama_timings_cache_and_reasoning_first_token(self):
        events = [
            {"choices": [{"delta": {"role": "assistant"}}]},
            {"choices": [{"delta": {"reasoning_content": "plan"}}]},
            {"choices": [{"delta": {"content": "answer"}}]},
            {"choices": [{"delta": {}, "finish_reason": "length"}],
             "timings": {"prompt_n": 80, "prompt_ms": 100, "predicted_n": 10, "predicted_ms": 500},
             "usage": {"prompt_tokens": 100, "completion_tokens": 10,
                       "prompt_tokens_details": {"cached_tokens": 20}}},
        ]
        with patch.object(perf.time, "perf_counter", side_effect=[0, .1, .2, .3, .7, .8, .9]):
            result = perf.streamed_chat(FakeAPI(events), {})
        self.assertAlmostEqual(result["ttft_ms"], 200)
        self.assertAlmostEqual(result["first_answer_ms"], 300)
        self.assertEqual(result["server_prefill_tps"], 800)
        self.assertEqual(result["server_decode_tps"], 20)
        self.assertEqual(result["cached_tokens"], 20)
        self.assertEqual(result["reasoning"], "plan")

    def test_strata_usage_only_does_not_invent_server_rates(self):
        events = [{"choices": [{"delta": {"content": "hello"}}]},
                  {"choices": [{"delta": {"content": " world"}}]},
                  {"choices": [{"delta": {}, "finish_reason": "stop"}]},
                  {"choices": [], "usage": {"prompt_tokens": 80, "completion_tokens": 8,
                   "prompt_tokens_details": {"cached_tokens": 0}}}]
        with patch.object(perf.time, "perf_counter", side_effect=[0, .1, .3, .4, .5, .6, .7]):
            result = perf.streamed_chat(FakeAPI(events), {})
        self.assertIsNone(result["server_prefill_tps"])
        self.assertIsNone(result["server_decode_tps"])
        self.assertAlmostEqual(result["prefill_estimate_tps"], 800)
        self.assertAlmostEqual(result["decode_estimate_tps"], 35)

    def test_partial_empty_and_error_streams_fail(self):
        content = {"choices": [{"delta": {"content": "partial"}}]}
        finish = {"choices": [{"delta": {}, "finish_reason": "stop"}]}
        for api in (FakeAPI([content], done=False), FakeAPI([content]),
                    FakeAPI([finish]), FakeAPI([{"error": {"message": "OOM"}}])):
            with self.subTest(api=api), self.assertRaises((ValueError, RuntimeError)):
                perf.streamed_chat(api, {})


class ResourceTests(unittest.TestCase):
    def test_attribution_and_simultaneous_total_peak(self):
        cards = "GPU-a, 0, Test A, 12000, 6000, 20, 60, 45\nGPU-b, 1, Test B, 12000, 3000, 30, 50, 44\n"
        clients = "GPU-a, 100, 2000\nGPU-a, 999, 3000\nGPU-b, 100, 1000\nGPU-b, 200, 1000\n"
        with patch.object(perf, "run_text", side_effect=[cards, clients]):
            snapshot = perf.nvidia_snapshot({100, 200})
        self.assertEqual(snapshot["GPU-a"]["process_mib"], 2000)
        self.assertEqual(snapshot["GPU-b"]["process_mib"], 2000)
        samples = [{"rss_mib": 80, "pss_mib": 60, "gpus": snapshot},
                   {"rss_mib": 90, "pss_mib": 65, "gpus": {
                       "GPU-a": {**snapshot["GPU-a"], "process_mib": 1000},
                       "GPU-b": {**snapshot["GPU-b"], "process_mib": 2500}}}]
        result = perf.resource_peaks(samples)
        self.assertEqual(result["vram_mib_peak"], 4000)  # not 2000 + 2500
        self.assertEqual(result["pss_mib_peak"], 65)
        self.assertEqual(result["gpus"]["GPU-a"]["free_mib_min"], 6000)

    def test_missing_process_memory_stays_unavailable(self):
        result = perf.resource_peaks([{"gpus": {"GPU-a": {
            "index": 0, "name": "test", "total_mib": 12000, "used_mib": 5000,
            "process_mib": None}}}])
        self.assertIsNone(result["vram_mib_peak"])
        self.assertIsNone(result["pss_mib_peak"])

    def test_hash_size_and_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.gguf"
            path.write_bytes(b"abc")
            discovered = perf.discover_model_files({"status": {"args": ["server", "--model", str(path)]}}, [])
            metadata = perf.model_metadata(discovered)[0]
        self.assertEqual(metadata["bytes"], 3)
        self.assertEqual(metadata["sha256"], "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")


class CLITests(unittest.TestCase):
    def test_streaming_http_to_artifacts_and_compare(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                data = json.dumps({"data": [{"id": "fixture"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/tokenize":
                    data = json.dumps({"tokens": body["content"].split()}).encode()
                    content_type = "application/json"
                else:
                    data = sse([{"choices": [{"delta": {"content": "Hello"}}]},
                                {"choices": [{"delta": {}, "finish_reason": "length"}],
                                 "usage": {"prompt_tokens": 128, "completion_tokens": 16,
                                           "prompt_tokens_details": {"cached_tokens": 0}}}])
                    content_type = "text/event-stream"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            output = Path(tmp) / "run"
            weight = Path(tmp) / "fixture.gguf"
            weight.write_bytes(b"synthetic metadata fixture")
            args = ["--base-url", f"http://127.0.0.1:{server.server_port}/v1",
                    "--model", "fixture", "--label", "fixture", "--pid", str(os.getpid()),
                    "--model-file", str(weight),
                    "--no-gpu", "--prompt-tokens", "128", "--output-tokens", "16",
                    "--repeats", "2", "--warmup", "1", "--output-dir", str(output)]
            self.assertEqual(perf.main(args), 0)
            report = json.loads((output / "summary.json").read_text())
            self.assertEqual(report["file_bytes"], weight.stat().st_size)
            self.assertEqual(len(report["model_files"][0]["sha256"]), 64)
            table = perf.render_table([{**g, "label": report["label"], "file_bytes": report["file_bytes"]}
                                       for g in report["groups"]], comparison=True)
            self.assertEqual(len({line.count("|") for line in table.splitlines()}), 1)
            self.assertEqual(report["groups"][0]["successful"], 2)
            self.assertEqual(len((output / "requests.jsonl").read_text().splitlines()), 3)
            self.assertTrue((output / "summary.csv").is_file())
            self.assertEqual(perf.main(["compare", str(output)]), 0)
            with self.assertRaisesRegex(ValueError, "already exists"):
                perf.main(args)

    def test_reserved_generation_fields_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()):
            for extra in ('{"n":2}', '{"stream":false}', '{"chat_template_kwargs":null}'):
                with self.subTest(extra=extra), self.assertRaises(SystemExit):
                    perf.parse_args(["--model", "m", "--label", "test", "--extra-body", extra])


if __name__ == "__main__":
    unittest.main()
