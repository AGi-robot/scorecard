#!/usr/bin/env python3
"""Thin proxy that forces thinking off for Qwen3.x models.

Forwards POST /v1/chat/completions to an upstream llama-server after
injecting chat_template_kwargs.enable_thinking=false, so Qwen3.x models are
measured under the same conditions as models without thinking mode
(BFCL/canvas protocol parity).

Usage: python no_think_proxy.py <upstream-base-url> <listen-port>
Example: python no_think_proxy.py http://127.0.0.1:8082 8092
"""
import json
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM = sys.argv[1].rstrip("/")
if UPSTREAM.endswith("/v1"):
    UPSTREAM = UPSTREAM[:-3]
PORT = int(sys.argv[2])


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        body.setdefault("chat_template_kwargs", {})["enable_thinking"] = False
        req = urllib.request.Request(
            UPSTREAM + self.path, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                data = r.read()
                code = r.status
        except urllib.error.HTTPError as e:
            data = e.read()
            code = e.code
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    print(f"no-think proxy: upstream={UPSTREAM} port={PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
