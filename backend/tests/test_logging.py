import logging
from io import StringIO

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.logging import (
    ReadableFormatter,
    RequestLoggingMiddleware,
    format_context,
    log_context,
)


def test_readable_formatter_should_include_event_context_and_duration() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        ReadableFormatter(
            "%(levelname)s %(message)s%(context_text)s"
        )
    )
    logger = logging.getLogger("test.readable_formatter")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    logger.info(
        "Detection completed",
        extra=log_context(
            "detection.completed",
            duration_ms=12.34,
            record_id=42,
            serial_no="SN123",
        ),
    )

    output = stream.getvalue()
    assert "INFO Detection completed" in output
    assert "duration_ms=12.34" in output
    assert "record_id=42" in output
    assert "serial_no=SN123" in output


def test_format_context_should_redact_sensitive_values() -> None:
    output = format_context(
        {
            "api_key": "secret-api-key",
            "password": "secret-password",
            "access_token": "secret-token",
            "serial_no": "SN123",
        }
    )

    assert "secret-api-key" not in output
    assert "secret-password" not in output
    assert "secret-token" not in output
    assert "api_key=[redacted]" in output
    assert "password=[redacted]" in output
    assert "access_token=[redacted]" in output
    assert "serial_no=SN123" in output


def test_request_logging_middleware_should_return_request_id_and_log_duration(caplog) -> None:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware, logger_name="test.request_logging")

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"status": "ok"}

    caplog.set_level(logging.INFO, logger="test.request_logging")
    response = TestClient(app).get("/ping", headers={"X-Request-ID": "req-test-1"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-test-1"
    assert any(record.event == "http.request_completed" for record in caplog.records)
    request_log = next(record for record in caplog.records if record.event == "http.request_completed")
    assert request_log.context["request_id"] == "req-test-1"
