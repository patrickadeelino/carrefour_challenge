"""Configuração opcional de exportadores OpenTelemetry para os serviços."""

from __future__ import annotations

import json
import logging
import os
from contextlib import suppress
from threading import Thread
from time import monotonic
from typing import Any

from opentelemetry import trace

_TRUE_VALUES = {"1", "true", "yes", "on"}
_SAFE_LOG_ATTRIBUTES = (
    "component",
    "duration_ms",
    "outcome",
    "error_code",
    "error_type",
)
_tracer_provider: Any | None = None
_logger_provider: Any | None = None
_httpx_instrumented = False


def configure_telemetry(service_name: str, logger_namespace: str) -> bool:
    """Configura logs JSON e exportadores OTLP quando explicitamente habilitados."""
    from .logging_config import configure_json_logging

    configure_json_logging(logger_namespace, service_name)
    if os.getenv("CARREFOUR_OTEL_ENABLED", "").strip().lower() not in _TRUE_VALUES:
        return False

    if _tracer_provider is None or _logger_provider is None:
        try:
            _configure_providers(service_name)
        except Exception:  # noqa: BLE001 - observability setup must fail open
            logging.getLogger(logger_namespace).warning(
                "telemetry.exporter.configuration_failed",
                extra={
                    "event_name": "telemetry.exporter.configuration_failed",
                    "component": "telemetry",
                    "error_code": "otel_configuration_failed",
                },
            )
            return False

    _configure_httpx_instrumentation(logger_namespace)

    # Recria os handlers para que o JSON local e a ponte OTLP usem o mesmo
    # escopo de eventos e respeitem a allowlist definida pelo formatador.
    configure_json_logging(logger_namespace, service_name)
    return True


def instrument_asgi_app(app: Any, logger_namespace: str) -> Any:
    """Adiciona spans de servidor ASGI e extrai o contexto W3C recebido."""
    if _tracer_provider is None:
        return app

    try:
        from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware

        return OpenTelemetryMiddleware(app)
    except Exception as error:  # noqa: BLE001 - tracing must not block serving
        logging.getLogger(logger_namespace).warning(
            "telemetry.instrumentation.configuration_failed",
            extra={
                "event_name": "telemetry.instrumentation.configuration_failed",
                "component": "asgi_middleware",
                "error_code": "asgi_instrumentation_failed",
                "error_type": type(error).__name__,
            },
        )
        return app


def _configure_httpx_instrumentation(logger_namespace: str) -> None:
    global _httpx_instrumented

    if _httpx_instrumented:
        return

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
        _httpx_instrumented = True
    except Exception as error:  # noqa: BLE001 - tracing must not block requests
        logging.getLogger(logger_namespace).warning(
            "telemetry.instrumentation.configuration_failed",
            extra={
                "event_name": "telemetry.instrumentation.configuration_failed",
                "component": "httpx_client",
                "error_code": "httpx_instrumentation_failed",
                "error_type": type(error).__name__,
            },
        )


def _configure_providers(service_name: str) -> None:
    global _tracer_provider, _logger_provider

    from opentelemetry._logs import set_logger_provider
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({"service.name": service_name})
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=_signal_endpoint("traces"), timeout=1.0)
        )
    )
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(endpoint=_signal_endpoint("logs"), timeout=1.0)
        )
    )

    trace.set_tracer_provider(tracer_provider)
    set_logger_provider(logger_provider)
    _tracer_provider = tracer_provider
    _logger_provider = logger_provider


def _signal_endpoint(signal_name: str) -> str:
    specific_endpoint = os.getenv(f"OTEL_EXPORTER_OTLP_{signal_name.upper()}_ENDPOINT")
    if specific_endpoint:
        return specific_endpoint
    base_endpoint = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318"
    )
    return f"{base_endpoint.rstrip('/')}/v1/{signal_name}"


def create_safe_log_handler(formatter: logging.Formatter) -> logging.Handler | None:
    """Retorna uma ponte OTLP que exporta apenas eventos e campos aprovados."""
    if _logger_provider is None:
        return None

    from opentelemetry.sdk._logs import LoggingHandler

    return _SafeOtelLogHandler(
        formatter,
        LoggingHandler(level=logging.NOTSET, logger_provider=_logger_provider),
    )


class _SafeOtelLogHandler(logging.Handler):
    """Filtra um LogRecord antes de entregá-lo à API de Logs do OpenTelemetry."""

    _carrefour_otel_log_handler = True

    def __init__(self, formatter: logging.Formatter, delegate: logging.Handler) -> None:
        super().__init__(level=logging.INFO)
        self._safe_formatter = formatter
        self._delegate = delegate

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = json.loads(self._safe_formatter.format(record))
            event_name = payload.get("event", "application.log")
            safe_record = logging.LogRecord(
                name=record.name,
                level=record.levelno,
                pathname="",
                lineno=0,
                msg=event_name,
                args=(),
                exc_info=None,
            )
            safe_record.created = record.created
            for field_name in _SAFE_LOG_ATTRIBUTES:
                value = payload.get(field_name)
                if isinstance(value, (str, int)) and not isinstance(value, bool):
                    setattr(safe_record, field_name, value)
            self._delegate.handle(safe_record)
        except Exception:  # noqa: BLE001 - discard telemetry-only failures
            # Telemetria não deve afetar o fluxo nem gerar logs recursivos.
            return


def shutdown_telemetry(timeout_millis: int = 1_000) -> None:
    """Tenta descarregar os lotes pendentes sem impedir o encerramento do app."""
    providers = tuple(
        provider
        for provider in (_logger_provider, _tracer_provider)
        if provider is not None
    )
    deadline = monotonic() + timeout_millis / 1_000
    for provider in providers:
        remaining_millis = max(round((deadline - monotonic()) * 1_000), 0)
        if remaining_millis == 0:
            break
        with suppress(Exception):
            provider.force_flush(timeout_millis=remaining_millis)

    def close_providers() -> None:
        for provider in providers:
            with suppress(Exception):
                provider.shutdown()

    shutdown_thread = Thread(target=close_providers, daemon=True)
    shutdown_thread.start()
    shutdown_thread.join(max(deadline - monotonic(), 0))
