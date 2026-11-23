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


MINISTRAL_ALIAS = alias_for_model_path(
    "Ministral-3-8B-Instruct-2512-BF16-abliterated.i1-IQ3_S.gguf"
)
SWIFT_ALIAS = alias_for_model_path(
    "Swift-1.5-Qwen3.8-27B-Uncensored-Dynamic-MTP-UD-IQ3_S.gguf"
)
