"""Model aliases derived from the shared llama.cpp router configuration."""
from __future__ import annotations

import configparser
from pathlib import Path

ROUTER_INI = Path(__file__).resolve().parents[3] / "models" / "llama-router.ini"


def alias_for_model_path(model_path_fragment: str) -> str:
    config = configparser.ConfigParser(interpolation=None)
    if not config.read(ROUTER_INI):
        raise RuntimeError(f"could not read model router config: {ROUTER_INI}")
    matches = [section for section in config.sections()
               if model_path_fragment in config.get(section, "model", fallback="")]
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one router model containing {model_path_fragment!r}, "
            f"found {matches} in {ROUTER_INI}"
        )
    return matches[0]


# Stable defaults allow standalone use without Grace's workspace. Explicit
# --model arguments remain the source of truth for an individual run.
MINISTRAL_ALIAS = "ministral-3-8b-instruct-2512-abliterated"
SWIFT_ALIAS = "swift15-qwen3.8-27b"
