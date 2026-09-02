from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any


request_id_context: ContextVar[str] = ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", request_id_context.get()),
        }
        for field in ("method", "path", "status", "duration_ms", "client"):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if not any(getattr(handler, "_negocial_json", False) for handler in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler._negocial_json = True  # type: ignore[attr-defined]
        handler.setFormatter(JsonFormatter())
        root.handlers.clear()
        root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def request_id(value: str | None = None) -> str:
    candidate = (value or "").strip()
    return candidate[:128] if candidate else uuid.uuid4().hex
