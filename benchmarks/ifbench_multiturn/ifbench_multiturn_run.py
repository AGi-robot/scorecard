#!/usr/bin/env python3
"""Deprecated entry point; use ../ifbench/ifbench_run.py --suite multiturn."""
import runpy
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.argv[0] = str(Path(__file__).resolve().parents[1] / "ifbench" / "ifbench_run.py")
    sys.argv.insert(1, "--suite")
    sys.argv.insert(2, "multiturn")
    runpy.run_path(sys.argv[0], run_name="__main__")
