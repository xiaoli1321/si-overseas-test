from __future__ import annotations

from contextvars import ContextVar
import logging
import sys
import time
from typing import Any
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_SENSITIVE_KEYS = (
    "api_key",
    "authorization",
    "dashscope_api_key",
    "jwt_secret",
    "password",
    "secret",
    "token",
)


class ReadableFormatter(logging.Formatter):
    """Formatter that keeps structured context readable in plain console logs."""

    def format(self, record: logging.LogRecord) -> str:
        if not hasattr(record, "event"):
            record.event = "app.log"
        if not hasattr(record, "context"):
            record.context = {}
        if isinstance(record.context, dict) and getattr(record, "duration_ms", None):
            record.context = {**record.context, "duration_ms": record.duration_ms}
        if isinstance(record.context, dict):
            context = format_context(record.context)
        else:
            context = str(record.context)
        if context == "-":
            record.context_text = ""
        elif isinstance(record.context, dict):
            record.context_text = f" | {context}"
        else:
            record.context_text = f" | {context}"
        return super().format(record)


def configure_logging(settings: Any) -> None:
    level = getattr(logging, str(settings.log_level).upper(), logging.INFO)
    if level < logging.INFO:
        level = logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(
        ReadableFormatter("%(asctime)s %(levelname)s %(message)s%(context_text)s")
    )

    for logger_name in ("src", "uvicorn.error"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def log_context(
    event: str, *, duration_ms: float | int | None = None, **context: Any
) -> dict[str, Any]:
    request_id = request_id_var.get()
    if request_id and "request_id" not in context:
        context["request_id"] = request_id
    extra: dict[str, Any] = {
        "event": event,
        "context": sanitize_context(context),
    }
    if duration_ms is not None:
        extra["duration_ms"] = round(float(duration_ms), 2)
    return extra


def format_context(context: dict[str, Any] | None) -> str:
    if not context:
        return "-"
    sanitized = sanitize_context(context)
    parts = []
    for key in sorted(sanitized):
        value = sanitized[key]
        if value is None:
            continue
        parts.append(f"{key}={value}")
    return " ".join(parts) if parts else "-"


def sanitize_context(context: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in context.items():
        if _is_sensitive_key(key):
            sanitized[key] = "[redacted]"
        elif isinstance(value, dict):
            sanitized[key] = format_context(value)
        elif isinstance(value, (list, tuple, set)):
            sanitized[key] = f"[{len(value)} items]"
        else:
            sanitized[key] = value
    return sanitized


def current_millis(start: float) -> float:
    return (time.perf_counter() - start) * 1000


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, logger_name: str = "src.api.requests") -> None:
        super().__init__(app)
        self.logger = logging.getLogger(logger_name)
        self.skip_paths = {"/", "/health"}

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            duration_ms = current_millis(start)
            request_id_var.reset(token)

        response.headers["X-Request-ID"] = request_id
        if request.url.path not in self.skip_paths:
            self.logger.info(
                f"{request.method} {request.url.path} -> {response.status_code} in {duration_ms:.0f}ms",
                extra=log_context(
                    "http.request_completed",
                    request_id=request_id,
                ),
            )
        return response


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(sensitive in lowered for sensitive in _SENSITIVE_KEYS)
