"""Configuração compartilhada de logs JSON seguros."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import ClassVar

from opentelemetry import trace

_request_id_context: ContextVar[str | None] = ContextVar(
    "carrefour_observability_request_id", default=None
)


@contextmanager
def bind_request_id(request_id: str) -> Iterator[None]:
    """Add a request identifier to log records in the current execution context."""
    token: Token[str | None] = _request_id_context.set(request_id)
    try:
        yield
    finally:
        _request_id_context.reset(token)


class JsonEventFormatter(logging.Formatter):
    """Serializa eventos com uma allowlist de campos operacionais."""

    _FIELD_TYPES: ClassVar[dict[str, type[str | int]]] = {
        "request_id": str,
        "component": str,
        "duration_ms": int,
        "outcome": str,
        "error_code": str,
        "error_type": str,
        "trace_id": str,
        "span_id": str,
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
            if field_name in {"trace_id", "span_id"}:
                value = _current_trace_id(field_name)
            if field_name == "request_id" and not isinstance(value, str):
                value = _request_id_context.get()
            if isinstance(value, field_type) and not isinstance(value, bool):
                payload[field_name] = value

        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _safe_string(value: object, default: str) -> str:
    return value if isinstance(value, str) else default


def configure_json_logging(logger_namespace: str, service_name: str) -> None:
    """Emite eventos JSON em stderr sem propagar conteúdo livre da mensagem."""
    logger = logging.getLogger(logger_namespace)
    for handler in tuple(logger.handlers):
        if isinstance(handler.formatter, JsonEventFormatter) or getattr(
            handler, "_carrefour_otel_log_handler", False
        ):
            logger.removeHandler(handler)
            handler.close()

    formatter = JsonEventFormatter(service_name)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    telemetry_handler = _telemetry_log_handler(formatter)
    if telemetry_handler is not None:
        logger.addHandler(telemetry_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def _current_trace_id(field_name: str) -> str | None:
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return None
    if field_name == "trace_id":
        return format(span_context.trace_id, "032x")
    return format(span_context.span_id, "016x")


def _telemetry_log_handler(
    formatter: JsonEventFormatter,
) -> logging.Handler | None:
    from .telemetry import create_safe_log_handler

    return create_safe_log_handler(formatter)
