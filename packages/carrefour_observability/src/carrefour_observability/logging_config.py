"""Configuração compartilhada de logs JSON seguros."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import ClassVar


class JsonEventFormatter(logging.Formatter):
    """Serializa eventos com uma allowlist de campos operacionais."""

    _FIELD_TYPES: ClassVar[dict[str, type[str | int]]] = {
        "component": str,
        "duration_ms": int,
        "outcome": str,
        "error_code": str,
        "error_type": str,
    }

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self._service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        event_name = getattr(record, "event_name", "application.log")
        payload: dict[str, str | int] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "service": self._service_name,
            "event": event_name,
            "component": _safe_string(
                getattr(record, "component", None), "application"
            ),
        }

        for field_name, field_type in self._FIELD_TYPES.items():
            if field_name == "component":
                continue
            value = getattr(record, field_name, None)
            if isinstance(value, field_type) and not isinstance(value, bool):
                payload[field_name] = value

        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _safe_string(value: object, default: str) -> str:
    return value if isinstance(value, str) else default


def configure_json_logging(logger_namespace: str, service_name: str) -> None:
    """Emite eventos JSON em stderr sem propagar conteúdo livre da mensagem."""
    logger = logging.getLogger(logger_namespace)
    for handler in tuple(logger.handlers):
        if isinstance(handler.formatter, JsonEventFormatter):
            logger.removeHandler(handler)
            handler.close()

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonEventFormatter(service_name))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
