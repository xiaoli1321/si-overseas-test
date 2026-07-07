"""Utility functions for the scanner package."""

from __future__ import annotations

import threading
from typing import Any, Optional

_print_lock = threading.Lock()

# Default pricing per 1M tokens (USD) for common models
MODEL_PRICING: dict[str, dict[str, float]] = {
    "qwen-vl-plus": {"input": 0.5, "output": 2.0},
    "qwen-vl-max": {"input": 2.0, "output": 6.0},
}


def _tprint(*args: Any, **kwargs: Any) -> None:
    with _print_lock:
        print(*args, **kwargs)


def normalize_expected(value: Any) -> tuple[Optional[str], Optional[bool]]:
    if isinstance(value, bool):
        return None, value
    if value is None:
        return None, False
    if isinstance(value, str) and value.strip():
        lowered = value.strip().lower()
        if lowered in {"normal", "none", "negative", "false"}:
            return None, False
        return value.strip(), True
    return None, None


def estimate_cost(model_name: str, scenario_count: int = 6) -> tuple[int, int, float]:
    input_tokens = 4500 * scenario_count
    output_tokens = 250 * scenario_count
    pricing = MODEL_PRICING.get(model_name)
    if pricing is None:
        raise KeyError(f"模型 '{model_name}' 未在 model_pricing 中配置")
    cost = (input_tokens / 1000000.0) * pricing["input"] + (
        output_tokens / 1000000.0
    ) * pricing["output"]
    return input_tokens, output_tokens, cost
