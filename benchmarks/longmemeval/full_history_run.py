#!/usr/bin/env python3
"""Run the LongMemEval full-history baseline against an OpenAI API endpoint.

The prompt layout and output schema follow the official LongMemEval generation
code. This is a long-context baseline; it does not ingest sessions into AIVA's
persistent memory store.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


DATASET_URLS = {
    "longmemeval_s_cleaned.json": (
        "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/"
        "resolve/main/longmemeval_s_cleaned.json"
    ),
    "longmemeval_oracle.json": (
        "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/"
        "resolve/main/longmemeval_oracle.json"
    ),
}


def ensure_dataset(path: Path) -> Path:
    """Download a supported LongMemEval dataset when its input file is absent."""
    if path.exists():
        return path
    url = DATASET_URLS.get(path.name)
    if url is None:
        raise SystemExit(
            f"Input file not found: {path}. Automatic download is available for: "
            f"{', '.join(DATASET_URLS)}"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {path.name} from Hugging Face...", flush=True)
    temp_path: Path | None = None
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
            ) as temp_file:
                temp_path = Path(temp_file.name)
                shutil.copyfileobj(response, temp_file)
        temp_path.replace(path)
    except (OSError, urllib.error.URLError) as error:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise SystemExit(f"Could not download {path.name}: {error}") from error
    print(f"Saved dataset to {path}", flush=True)
    return path


def build_prompt(entry: dict) -> str:
    """Build the official full-history session prompt for one LongMemEval item."""
    sessions = entry["haystack_sessions"]
    dates = entry["haystack_dates"]
    blocks = []
    for index, (date, session) in enumerate(zip(dates, sessions), start=1):
        clean_session = [
            {"role": turn["role"], "content": turn["content"]}
            for turn in session
        ]
        blocks.append(
            f"\n### Session {index}:\nSession Date: {date}\n"
            f"Session Content:\n{json.dumps(clean_session, ensure_ascii=False)}\n"
        )
    history = "".join(blocks)
    return (
        "I will give you several history chats between you and a user. "
        "Please answer the question based on the relevant chat history.\n\n\n"
        f"History Chats:\n\n{history}\n"
        f"Current Date: {entry['question_date']}\n"
        f"Question: {entry['question']}\nAnswer:"
    )


def complete(base_url: str, model: str, prompt: str, api_key: str,
             max_tokens: int, timeout: float) -> str:
    url = base_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body["choices"][0]["message"].get("content", "").strip()


def load_entries(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        return [json.loads(line) for line in raw.splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Official LongMemEval JSON file")
    parser.add_argument("--output", required=True, type=Path, help="Official-compatible hypothesis JSONL")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/v1")
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY", "EMPTY"))
    parser.add_argument("--limit", type=int, help="Run only the first N items")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many items")
    parser.add_argument("--max-tokens", type=int, default=500)
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--overwrite", action="store_true", help="Discard existing output instead of resuming")
    args = parser.parse_args()

    args.input = ensure_dataset(args.input)
    entries = load_entries(args.input)
    selected = entries[args.offset:]
    if args.limit is not None:
        selected = selected[:args.limit]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    completed: set[str] = set()
    if args.output.exists() and not args.overwrite:
        for line in args.output.read_text(encoding="utf-8").splitlines():
            if line.strip():
                completed.add(str(json.loads(line)["question_id"]))
    mode = "w" if args.overwrite else "a"
    with args.output.open(mode, encoding="utf-8") as output:
        for index, entry in enumerate(selected, start=args.offset + 1):
            question_id = str(entry["question_id"])
            if question_id in completed:
                continue
            started = time.monotonic()
            try:
                hypothesis = complete(
                    args.base_url, args.model, build_prompt(entry), args.api_key,
                    args.max_tokens, args.timeout,
                )
            except urllib.error.HTTPError as error:
                details = error.read().decode("utf-8", "replace")[:500]
                raise SystemExit(f"Request failed for {question_id}: HTTP {error.code}: {details}") from error
            row = {"question_id": question_id, "hypothesis": hypothesis}
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
            output.flush()
            completed.add(question_id)
            elapsed = time.monotonic() - started
            print(f"[{index}/{len(entries)}] {question_id}: {elapsed:.1f}s", flush=True)


if __name__ == "__main__":
    main()
