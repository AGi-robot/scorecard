#!/usr/bin/env python3
"""Score Mind's SQLite conversation window on BFCL V4 memory questions.

This is a component adapter, not an official BFCL memory-tool run. It uses
Mind's public ConversationStore API directly and calls the selected model
through an OpenAI-compatible endpoint. It does not import or launch Grace's
runtime, chat node, persona, or tool orchestration.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def user_messages(question: list) -> list[str]:
    """Flatten a BFCL question's user messages in transcript order."""
    messages: list[str] = []
    for turn in question or []:
        turn_messages = turn if isinstance(turn, list) else [turn]
        for message in turn_messages:
            if isinstance(message, dict) and message.get("role") == "user":
                content = message.get("content", "")
                if isinstance(content, str) and content.strip():
                    messages.append(content.strip())
    return messages


def load_conversation_store(mind_root: Path):
    memory_module = mind_root / "src/memory/conversation.py"
    if not memory_module.is_file():
        raise SystemExit(f"Mind ConversationStore source not found: {memory_module}")
    spec = importlib.util.spec_from_file_location("scorecard_mind_conversation", memory_module)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load Mind ConversationStore from {memory_module}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ConversationStore, memory_module


def load_official_checker(bfcl_root: Path):
    package_root = bfcl_root / "bfcl_eval"
    if not package_root.is_dir():
        raise SystemExit(f"BFCL package directory not found under {bfcl_root}")
    sys.path.insert(0, str(bfcl_root))
    try:
        from bfcl_eval.eval_checker.agentic_eval.agentic_checker import agentic_checker
    except ImportError as error:
        raise SystemExit(
            "Cannot import BFCL's official agentic answer checker. Install the "
            "pinned BFCL checkout with `python -m pip install -e .` first."
        ) from error
    return agentic_checker


def completion(
    base_url: str,
    model: str,
    api_key: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    timeout: float,
) -> str:
    url = base_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
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
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", "replace")[:1000]
        raise RuntimeError(f"LLM endpoint returned HTTP {error.code}: {details}") from error
    try:
        text = body["choices"][0]["message"].get("content", "")
    except (KeyError, IndexError, TypeError) as error:
        raise RuntimeError("LLM endpoint returned an unexpected chat completion") from error
    if not isinstance(text, str):
        raise RuntimeError("LLM endpoint returned a non-text message")
    return text.strip()


def messages_for(memory, system_prompt: str, user_text: str) -> list[dict[str, str]]:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(memory.recent())
    messages.append({"role": "user", "content": user_text})
    return messages


def get_seed_cache(path: Path, signature: str) -> dict[int, dict]:
    cached: dict[int, dict] = {}
    if not path.is_file():
        return cached
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("signature") != signature:
            return {}
        cached[int(row["index"])] = row
    return cached


def replay_scenario(
    scenario: str,
    prereq_entries: list[dict],
    memory_class,
    system_prompt: str,
    base_url: str,
    model: str,
    api_key: str,
    memory_turns: int,
    seed_max_tokens: int,
    timeout: float,
    cache_path: Path,
    signature: str,
    db_path: Path,
) -> object:
    db_path.unlink(missing_ok=True)
    memory = memory_class(str(db_path), max_turns=memory_turns)
    seed_cache = get_seed_cache(cache_path, signature)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cached_indexes = set(seed_cache)
    cache_file = cache_path.open("a" if cached_indexes else "w", encoding="utf-8")
    index = 0
    try:
        for entry in prereq_entries:
            for user_text in user_messages(entry.get("question", [])):
                cached = seed_cache.get(index)
                if cached and cached.get("user") == user_text:
                    assistant_text = cached["assistant"]
                else:
                    prompt = messages_for(memory, system_prompt, user_text)
                    assistant_text = completion(
                        base_url, model, api_key, prompt, seed_max_tokens, timeout
                    )
                    row = {
                        "index": index,
                        "signature": signature,
                        "user": user_text,
                        "assistant": assistant_text,
                    }
                    cache_file.write(json.dumps(row, ensure_ascii=False) + "\n")
                    cache_file.flush()
                memory.add_exchange(user_text, assistant_text)
                index += 1
    finally:
        cache_file.close()
    return memory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mind-root", required=True, type=Path, help="Mind repository checkout root")
    parser.add_argument(
        "--bfcl-root", required=True, type=Path,
        help="Pinned berkeley-function-call-leaderboard checkout root",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/v1")
    parser.add_argument("--model", default="ministral-3-14b-instruct-2512")
    parser.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY", "EMPTY"))
    parser.add_argument("--memory-turns", type=int, default=8)
    parser.add_argument("--system-prompt-file", type=Path,
                        help="optional frozen prompt file; omitted for a bare-model memory run")
    parser.add_argument("--max-tokens", type=int, default=500)
    parser.add_argument("--seed-max-tokens", type=int, default=256)
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--limit", type=int, help="Score only the first N questions")
    parser.add_argument("--label", default="ministral3-14b-memory8")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    mind_root = args.mind_root.resolve()
    bfcl_root = args.bfcl_root.resolve()
    bfcl_data = bfcl_root / "bfcl_eval" / "data"
    questions_path = bfcl_data / "BFCL_v4_memory.json"
    answers_path = bfcl_data / "possible_answer" / "BFCL_v4_memory.json"
    prereq_dir = bfcl_data / "memory_prereq_conversation"
    for path in (questions_path, answers_path, prereq_dir):
        if not path.exists():
            raise SystemExit(f"BFCL V4 data is missing: {path}")

    memory_class, memory_source = load_conversation_store(mind_root)
    agentic_checker = load_official_checker(bfcl_root)
    system_prompt = args.system_prompt_file.read_text(encoding="utf-8").strip() \
        if args.system_prompt_file else ""
    question_entries = read_jsonl(questions_path)
    answer_entries = read_jsonl(answers_path)
    answers = {str(row["id"]): row.get("ground_truth", []) for row in answer_entries}
    if args.limit is not None:
        question_entries = question_entries[:max(0, args.limit)]

    output_path = args.output or Path("benchmarks/bfcl/results/v4") / f"mind_recent_{args.label}.jsonl"
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if args.overwrite:
        output_path.unlink(missing_ok=True)
    completed = {}
    if output_path.is_file():
        completed = {
            str(row["id"]): row
            for row in read_jsonl(output_path)
        }
    remaining = [row for row in question_entries if str(row["id"]) not in completed]
    scenarios = sorted({str(row["scenario"]) for row in remaining})

    memory_hash = hashlib.sha256(memory_source.read_bytes()).hexdigest()
    questions_hash = hashlib.sha256(questions_path.read_bytes()).hexdigest()
    prereq_hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(prereq_dir.glob("memory_*.json"))
    }
    system_hash = hashlib.sha256(system_prompt.encode()).hexdigest() if system_prompt else None
    seed_config = {
        "mind_conversation_source": memory_hash,
        "bfcl_questions": questions_hash,
        "bfcl_prerequisites": prereq_hashes,
        "base_url": args.base_url,
        "model": args.model,
        "system_prompt": system_hash,
        "memory_turns": args.memory_turns,
        "seed_max_tokens": args.seed_max_tokens,
    }
    signature = hashlib.sha256(json.dumps(seed_config, sort_keys=True).encode()).hexdigest()
    result_config = {
        "seed_signature": signature,
        "answers_sha256": hashlib.sha256(answers_path.read_bytes()).hexdigest(),
        "max_tokens": args.max_tokens,
    }
    result_signature = hashlib.sha256(json.dumps(result_config, sort_keys=True).encode()).hexdigest()
    for row in completed.values():
        saved_signature = row.get("run_signature")
        if saved_signature != result_signature:
            raise SystemExit("Existing results use a different run configuration. Choose a new label or use --overwrite.")
    cache_dir = output_path.parent / "seed_cache"

    output_mode = "a" if output_path.exists() else "w"
    with tempfile.TemporaryDirectory(prefix="mind-bfcl-memory-") as temporary:
        with output_path.open(output_mode, encoding="utf-8") as output:
            for scenario in scenarios:
                prereq_path = prereq_dir / f"memory_{scenario}.json"
                if not prereq_path.is_file():
                    raise SystemExit(f"No BFCL memory prerequisites found for {scenario}: {prereq_path}")
                prereq_entries = read_jsonl(prereq_path)
                db_path = Path(temporary) / f"{scenario}.sqlite3"
                cache_path = cache_dir / f"{args.label}_{scenario}.jsonl"
                print(f"Seeding {scenario} history through Mind ConversationStore...", flush=True)
                memory = replay_scenario(
                    scenario, prereq_entries, memory_class, system_prompt,
                    args.base_url, args.model, args.api_key, args.memory_turns,
                    args.seed_max_tokens, args.timeout, cache_path, signature, db_path,
                )
                scenario_questions = [
                    row for row in remaining if str(row["scenario"]) == scenario
                ]
                for row in scenario_questions:
                    question_id = str(row["id"])
                    prompts = user_messages(row.get("question", []))
                    if not prompts:
                        response = ""
                        valid = False
                    else:
                        response = completion(
                            args.base_url, args.model, args.api_key,
                            messages_for(memory, system_prompt, "\n".join(prompts)),
                            args.max_tokens, args.timeout,
                        )
                        score = agentic_checker(response, answers.get(question_id, []))
                        valid = bool(score.get("valid"))
                    result = {
                        "id": question_id,
                        "scenario": scenario,
                        "response": response,
                        "possible_answers": answers.get(question_id, []),
                        "valid": valid,
                        "memory_turns": args.memory_turns,
                        "model": args.model,
                        "run_signature": result_signature,
                    }
                    output.write(json.dumps(result, ensure_ascii=False) + "\n")
                    output.flush()
                    completed[question_id] = result
                    print(f"{question_id}: {'PASS' if valid else 'FAIL'}", flush=True)

    all_rows = [completed[str(row["id"])] for row in question_entries if str(row["id"]) in completed]
    summary = {
        "benchmark": "Mind ConversationStore recent-window track on BFCL V4 memory QA",
        "official_bfcl_memory_score": False,
        "model": args.model,
        "memory_turns": args.memory_turns,
        "questions": len(all_rows),
        "correct": sum(bool(row.get("valid")) for row in all_rows),
        "accuracy": round(sum(bool(row.get("valid")) for row in all_rows) / len(all_rows), 4)
        if all_rows else 0.0,
        "memory_implementation": "Mind ConversationStore.recent/add_exchange",
        "memory_source_sha256": memory_hash,
        "run_signature": result_signature,
        "bfcl_questions_sha256": questions_hash,
        "bfcl_prerequisite_sha256": prereq_hashes,
        "system_prompt_sha256": system_hash,
        "temperature": 0,
        "max_tokens": args.max_tokens,
        "seed_max_tokens": args.seed_max_tokens,
        "answer_scorer": "BFCL agentic_checker",
        "generated_at_unix": int(time.time()),
    }
    summary_path = output_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
