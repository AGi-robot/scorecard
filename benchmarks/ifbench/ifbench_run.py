#!/usr/bin/env python3
"""Single-turn and multi-turn IFBench baselines with pinned official data and verifiers."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ifbench_baseline import run

if __name__ == "__main__":
    run()
