#!/usr/bin/env python3
"""Launch a pinned official EQ-Bench v4 or Creative Writing v3 checkout.

This adapter does not reinterpret either benchmark's prompts or scores.
Arguments after -- are passed to the official runner unchanged.
"""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def main(argv=None):
    protocols = json.loads((HERE / "protocols.json").read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", required=True, choices=protocols)
    parser.add_argument("--checkout", required=True, type=Path)
    parser.add_argument("--python", default=sys.executable,
                        help="Python executable in the official environment")
    parser.add_argument("--dry-run", action="store_true",
                        help="Verify the checkout and print the command; make no API calls")
    parser.add_argument("official_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    checkout = args.checkout.resolve()
    protocol = protocols[args.suite]
    try:
        revision = subprocess.check_output(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(
            ["git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=no"],
            text=True).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        parser.error(f"Cannot inspect official checkout: {exc}")
    if revision != protocol["revision"]:
        parser.error(f"Expected official revision {protocol['revision']}; got {revision}")
    if dirty:
        parser.error("Official tracked files were modified; use a clean pinned checkout")
    entry = checkout / protocol["entrypoint"]
    if not entry.is_file():
        parser.error(f"Missing official runner: {entry}")
    forwarded = args.official_args
    if forwarded[:1] == ["--"]:
        forwarded = forwarded[1:]
    if not forwarded:
        parser.error("Pass official arguments after -- (or --help for official usage)")
    command = [args.python, str(entry), *forwarded]
    print(f"{args.suite}: {revision}", flush=True)
    if args.dry_run:
        print(shlex.join(command))
        return 0
    return subprocess.call(command, cwd=checkout)


if __name__ == "__main__":
    raise SystemExit(main())
