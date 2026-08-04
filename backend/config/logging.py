"""Structured logging (00 §12).

JSON to stdout in production, human-readable in development. Every line carries the
request id so a log line can be joined to the audit row for the same request.

No dependency is added for this: a formatter is twenty lines, and 00 §3 forbids
dependencies without a named requirement.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from core.context import get_request_id

_RESERVED = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}

# Never logged, at any level (SEC-3, FR-AUD-006).
_REDACT = {
    "password",
    "passwd",
    "secret",
    "token",
    "access",
    "refresh",
    "authorization",
    "api_key",
    "code_hash",
    "otp",
    "code",
    "session",
    "csrf",
}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("[redacted]" if k.lower() in _REDACT else _redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    """One JSON object per line, to stdout."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = _redact(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(_redact(payload), default=str, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Readable during development. Never used in production (prod.py asserts it)."""

    def format(self, record: logging.LogRecord) -> str:
        rid = get_request_id()
        prefix = f"[{rid[:8]}] " if rid else ""
        return f"{record.levelname:<8} {prefix}{record.name}: {record.getMessage()}"


def build_logging_config(level: str, fmt: str) -> dict[str, Any]:
    formatter = "json" if fmt == "json" else "console"
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {"()": "config.logging.JsonFormatter"},
            "console": {"()": "config.logging.ConsoleFormatter"},
        },
        # stdout only — never a file inside a container (00 §12)
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": formatter,
            }
        },
        "root": {"handlers": ["stdout"], "level": level},
        "loggers": {
            "django": {"handlers": ["stdout"], "level": level, "propagate": False},
            "django.db.backends": {"level": "WARNING", "propagate": False},
            "districore": {"handlers": ["stdout"], "level": level, "propagate": False},
        },
    }
