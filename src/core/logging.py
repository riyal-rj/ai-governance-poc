"""Central structured logging configuration."""

from __future__ import annotations

import json
import logging
import logging.config
import traceback
from datetime import UTC, datetime
from typing import Any

from src.core.request_context import get_request_id

_EXTRA_FIELDS = (
    "component",
    "dependency",
    "duration_ms",
    "event",
    "method",
    "path",
    "route",
    "status_code",
)


class JsonFormatter(logging.Formatter):
    """Emit one json per object per record for loki or any log collector"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }
        for field in _EXTRA_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info:
            payload["exception"] = "".join(traceback.format_exception(*record.exc_info))
        return json.dumps(payload, default=str, separators=(",", ":"))


class TextFormatter(logging.Formatter):
    """Human readable local formatter retaining the request ID"""

    def format(self, record: logging.LogRecord) -> str:
        original_message = record.getMessage()
        original_msg = record.msg
        original_args = record.args
        record.msg = f"request_id={get_request_id()} {original_message}"
        record.args = ()
        try:
            return super().format(record)
        finally:
            record.msg = original_msg
            record.args = original_args


def configure_logging(*, level: str, json_logs: bool) -> None:
    """Configuring the root logging once during the FastAPI lifespan startup."""

    formatter_name = "json" if json_logs else "text"
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {"()": JsonFormatter},
                "text": {
                    "()": TextFormatter,
                    "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
                },
            },
            "handlers": {
                "stdout": {
                    "class": "logging.StreamHandler",
                    "formatter": formatter_name,
                    "stream": "ext://sys.stdout",
                }
            },
            "root": {"handlers": ["stdout"], "level": level},
            "loggers": {"uvicorn.access": {"handlers": [], "propagate": False}},
        }
    )
