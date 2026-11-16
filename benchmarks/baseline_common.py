"""Shared transport and provenance for the pinned baseline integrations."""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent


def read_jsonl(path):
    with Path(path).open() as source:
        return [json.loads(line) for line in source if line.strip()]


def write_json(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def download(url, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        tmp = path.with_suffix(path.suffix + ".tmp")
        with urllib.request.urlopen(url, timeout=120) as response, tmp.open("wb") as out:
            shutil.copyfileobj(response, out)
        tmp.replace(path)
    return path


def checkout(url, revision, directory):
    directory = Path(directory).resolve()
    if not directory.exists():
        subprocess.run(["git", "clone", url, str(directory)], check=True)
        subprocess.run(["git", "-C", str(directory), "checkout", "--detach", revision], check=True)
    actual = subprocess.check_output(["git", "-C", str(directory), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(directory), "status", "--porcelain", "--untracked-files=no"], text=True)
    if actual != revision or dirty:
        raise ValueError(f"Official checkout must be clean at {revision}: {directory}")
    return directory


def parser(description, default_n=1, temperature=0.0, max_tokens=8192):
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--stage", choices=["prepare", "generate", "score", "all"], default="all")
    p.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL"))
    p.add_argument("--model", default=os.environ.get("BENCHMARK_MODEL"))
    p.add_argument("--output", type=Path, required=True, help="Dedicated directory; resume requires identical configuration")
    p.add_argument("--official", type=Path, help="Existing clean pinned official checkout (otherwise cloned into benchmarks/.cache)")
    p.add_argument("--limit", type=int, default=0, help="Smoke subset size; 0 means full dataset")
    p.add_argument("--n", type=int, default=default_n)
    p.add_argument("--temperature", type=float, default=temperature)
    p.add_argument("--max-tokens", type=int, default=max_tokens)
    p.add_argument("--request-timeout", type=int, default=300)
    return p


def complete(args, messages, top_p=1.0):
    body = {"model": args.model, "messages": messages, "temperature": args.temperature,
            "top_p": top_p, "max_tokens": args.max_tokens, "n": 1, "stream": False}
    headers = {"Content-Type": "application/json"}
    if os.environ.get("OPENAI_API_KEY"):
        headers["Authorization"] = "Bearer " + os.environ["OPENAI_API_KEY"]
    for attempt in range(4):
        req = urllib.request.Request(args.base_url.rstrip("/") + "/chat/completions",
                                     data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=args.request_timeout) as r:
                choice = json.load(r)["choices"][0]
            content = choice["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Endpoint returned no final text; configure reasoning output explicitly")
            if choice.get("finish_reason") != "stop":
                raise ValueError("Incomplete completion; increase --max-tokens in a new output directory")
            return content
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise RuntimeError(f"Endpoint HTTP {error.code}; no score written") from None
            time.sleep(min(30, 2 ** attempt))
    raise RuntimeError("No completion")


def initialize(args, protocol, data_path, total):
    if args.limit < 0 or args.n < 1 or args.max_tokens < 1:
        raise ValueError("limit must be nonnegative; n and max-tokens must be positive")
    if args.stage in ("generate", "all") and (not args.base_url or not args.model):
        raise ValueError("Generation requires --base-url and --model (or OPENAI_BASE_URL and BENCHMARK_MODEL)")
    if args.base_url:
        url = urlsplit(args.base_url)
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("Use an HTTP(S) base URL without credentials, query, or fragment")
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    config = {"protocol": protocol, "data_sha256": digest(data_path), "total": total,
              "limit": args.limit, "model": args.model, "base_url": args.base_url,
              "n": args.n, "temperature": args.temperature, "max_tokens": args.max_tokens}
    path = args.output / "manifest.json"
    if path.exists() and json.loads(path.read_text()) != config:
        raise ValueError("Output configuration differs; use a new directory and identical flags for every stage")
    write_json(path, config)
    return config


def responses(args, tasks, messages, top_p=1.0):
    """Checkpoint successful samples only; reject stale, duplicate, or incomplete data."""
    path = args.output / "responses.jsonl"
    records = read_jsonl(path) if path.exists() else []
    have = {}
    expected = {str(t["id"]): t for t in tasks}
    for row in records:
        key = (str(row["id"]), row["sample"])
        if key in have or key[0] not in expected or not 0 <= key[1] < args.n:
            raise ValueError("Unexpected or duplicate response")
        if not isinstance(row["response"], str) or not row["response"].strip():
            raise ValueError("Invalid response")
        have[key] = row["response"]
    if args.stage in ("generate", "all"):
        with path.open("a") as out:
            for task in tasks:
                prompt_messages = None
                for sample in range(args.n):
                    key = (str(task["id"]), sample)
                    if key in have:
                        continue
                    if prompt_messages is None:
                        prompt_messages = messages(task)
                    text = complete(args, prompt_messages, top_p)
                    row = {"id": key[0], "sample": sample, "response": text}
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
                    out.flush()
                    have[key] = text
                    print(f"Saved {len(have)}/{len(tasks) * args.n}", flush=True)
    if args.stage in ("score", "all") and len(have) != len(tasks) * args.n:
        raise ValueError("Incomplete generation; refusing to score a partial run")
    return [[have[(str(t["id"]), i)] for i in range(args.n)] for t in tasks] if args.stage in ("score", "all") else None
