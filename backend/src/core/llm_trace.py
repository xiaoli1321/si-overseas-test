"""LangChain callback handler for detailed LLM I/O logging.

Usage:

    from src.core.llm_trace import LlmTraceCallback

    callback = LlmTraceCallback(tag="detector")
    response = structured_llm.invoke(messages, config={"callbacks": [callback]})

Logs are emitted as structured JSON via the standard logger at INFO level.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from src.core.logging import log_context

logger = logging.getLogger(__name__)


class LlmTraceCallback(BaseCallbackHandler):
    """LangChain callback that logs full LLM prompts and responses as structured JSON."""

    def __init__(self, tag: str = "llm") -> None:
        self.tag = tag
        self._start: float | None = None

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        **kwargs: Any,
    ) -> None:
        self._start = time.perf_counter()
        # Extract messages from kwargs if available (langchain >= 0.1 passes them as "invocation_params")
        messages: list[dict[str, Any]] | None = None
        invocation_params = serialized.get("invocation_params", {})
        model = invocation_params.get("model", "unknown")

        # Try to get messages from kwargs (langchain passes them for chat models)
        if "inputs" in kwargs:
            inputs = kwargs["inputs"]
            if isinstance(inputs, list):
                messages = _summarize_messages(inputs)

        log_data: dict[str, Any] = {
            "tag": self.tag,
            "model": model,
        }
        if prompts:
            log_data["prompts"] = [p[:2000] for p in prompts]
        if messages:
            log_data["messages"] = messages

        logger.info(
            "LLM call started",
            extra=log_context(f"llm_trace.{self.tag}.start", **log_data),
        )

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        elapsed = (time.perf_counter() - self._start) if self._start else 0.0
        generations = response.llm_output or {}
        model = generations.get("model_name", "unknown")
        token_usage = generations.get("token_usage", {})

        # Summarize each generation
        outputs: list[dict[str, Any]] = []
        for gen_list in response.generations:
            for gen in gen_list:
                text = gen.text
                # Truncate very long responses
                outputs.append(
                    {
                        "text": text[:5000] if text else "",
                        "generation_info": gen.generation_info or {},
                    }
                )

        log_data: dict[str, Any] = {
            "tag": self.tag,
            "model": model,
            "duration_ms": round(elapsed * 1000, 1),
            "outputs": outputs,
        }
        if token_usage:
            log_data["token_usage"] = token_usage

        logger.info(
            "LLM call completed",
            extra=log_context(f"llm_trace.{self.tag}.end", **log_data),
        )

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        elapsed = (time.perf_counter() - self._start) if self._start else 0.0
        logger.error(
            "LLM call failed",
            extra=log_context(
                f"llm_trace.{self.tag}.error",
                tag=self.tag,
                duration_ms=round(elapsed * 1000, 1),
                error=str(error),
            ),
        )


def _summarize_messages(
    inputs: list[Any],
) -> list[dict[str, Any]]:
    """Convert langchain message list to a JSON-safe summary.

    Strips image data to keep logs readable.
    """
    summarized: list[dict[str, Any]] = []
    for msg in inputs:
        entry: dict[str, Any] = {"type": type(msg).__name__}
        content = getattr(msg, "content", "")
        if isinstance(content, str):
            entry["text"] = content[:2000]
        elif isinstance(content, list):
            text_parts: list[str] = []
            image_count = 0
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        text_parts.append(str(part.get("text", ""))[:2000])
                    elif part.get("type") == "image_url":
                        image_count += 1
            entry["text"] = " ".join(text_parts)
            if image_count:
                entry["image_count"] = image_count
        summarized.append(entry)
    return summarized
