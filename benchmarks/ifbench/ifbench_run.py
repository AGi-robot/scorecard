#!/usr/bin/env python3
"""Single-turn IFBench baseline with pinned official data and verifiers."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ifbench_baseline import run

if __name__ == "__main__":
    import argparse
    import sys
    args, rest = argparse.ArgumentParser(add_help=False).parse_known_args()
    del args
    if "--suite" in rest:
        index = rest.index("--suite")
        suite = rest[index + 1]
        if suite not in ("single", "multiturn"):
            raise SystemExit("--suite must be single or multiturn")
        del rest[index:index + 2]
    else:
        suite = "single"
    sys.argv = [sys.argv[0], *rest]
    run(multiturn=suite == "multiturn")
