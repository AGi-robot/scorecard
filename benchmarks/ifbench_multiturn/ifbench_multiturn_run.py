#!/usr/bin/env python3
"""Fixed-history IFBench multi-turn baseline, separate from single-turn."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ifbench_baseline import run

if __name__ == "__main__":
    run(multiturn=True)
