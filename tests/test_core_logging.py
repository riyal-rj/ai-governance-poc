from __future__ import annotations

import json
import logging

from src.core.logging import JsonFormatter, TextFormatter, configure_logging
from src.core.request_context import bind_request_id, reset_request_id


def _make_record(msg: str = "hello", **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="finassist.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


class TestJsonFormatter:
    def test_emits_valid_json_with_core_fields(self) -> None:
        token = bind_request_id("req-123")
        try:
            payload = json.loads(JsonFormatter().format(_make_record("hello")))
        finally:
            reset_request_id(token)

        assert payload["message"] == "hello"
        assert payload["severity"] == "INFO"
        assert payload["logger"] == "finassist.test"
        assert payload["request_id"] == "req-123"

    def test_includes_known_extra_fields_only(self) -> None:
        record = _make_record("event happened", event="thing", route="/health/live", unlisted="x")
        payload = json.loads(JsonFormatter().format(record))
        assert payload["event"] == "thing"
        assert payload["route"] == "/health/live"
        assert "unlisted" not in payload

    def test_includes_exception_traceback(self) -> None:
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="t",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="failed",
                args=(),
                exc_info=sys.exc_info(),
            )
        payload = json.loads(JsonFormatter().format(record))
        assert "ValueError" in payload["exception"]


class TestTextFormatter:
    def test_prefixes_request_id_and_restores_record(self) -> None:
        token = bind_request_id("req-abc")
        try:
            record = _make_record("plain message")
            original_msg = record.msg
            formatted = TextFormatter().format(record)
        finally:
            reset_request_id(token)

        assert "request_id=req-abc plain message" in formatted
        assert record.msg == original_msg


def test_configure_logging_json_mode_does_not_raise() -> None:
    configure_logging(level="INFO", json_logs=True)
    assert isinstance(logging.getLogger().handlers[0].formatter, JsonFormatter)


def test_configure_logging_text_mode_does_not_raise() -> None:
    configure_logging(level="DEBUG", json_logs=False)
    assert isinstance(logging.getLogger().handlers[0].formatter, TextFormatter)


def test_configure_logging_silences_uvicorn_access() -> None:
    configure_logging(level="INFO", json_logs=True)
    uvicorn_access = logging.getLogger("uvicorn.access")
    assert uvicorn_access.propagate is False
    assert uvicorn_access.handlers == []
