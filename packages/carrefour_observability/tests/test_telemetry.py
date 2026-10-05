import json
import logging

from carrefour_observability import telemetry
from carrefour_observability.logging_config import JsonEventFormatter
from carrefour_observability.telemetry import (
    _SafeOtelLogHandler,
    _signal_endpoint,
    configure_telemetry,
)


class _CaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_safe_otel_log_handler_exports_only_approved_fields() -> None:
    capture = _CaptureHandler()
    handler = _SafeOtelLogHandler(JsonEventFormatter("assistant-runtime"), capture)
    record = logging.LogRecord(
        name="carrefour_runtime.process",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="synthetic patient marker",
        args=(),
        exc_info=None,
    )
    record.event_name = "process.started"
    record.component = "process_service"
    record.patient_name = "private marker"
    record.image_id = "private image id"

    handler.emit(record)

    assert len(capture.records) == 1
    safe_record = capture.records[0]
    assert safe_record.getMessage() == "process.started"
    assert safe_record.component == "process_service"
    assert not hasattr(safe_record, "patient_name")
    assert not hasattr(safe_record, "image_id")
    assert "synthetic patient marker" not in json.dumps(safe_record.__dict__)


def test_signal_endpoint_uses_signal_override_or_base_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318/")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    assert _signal_endpoint("traces") == "http://collector:4318/v1/traces"

    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", "http://collector:4318/custom/logs"
    )
    assert _signal_endpoint("logs") == "http://collector:4318/custom/logs"


def test_telemetry_configuration_failure_keeps_json_logging(
    monkeypatch, capsys
) -> None:
    namespace = "carrefour_observability.telemetry_test"
    logger = logging.getLogger(namespace)
    monkeypatch.setenv("CARREFOUR_OTEL_ENABLED", "true")
    monkeypatch.setattr(telemetry, "_tracer_provider", None)
    monkeypatch.setattr(telemetry, "_logger_provider", None)

    def fail_configuration(_service_name: str) -> None:
        raise RuntimeError("collector credential should never be logged")

    monkeypatch.setattr(
        "carrefour_observability.telemetry._configure_providers",
        fail_configuration,
    )

    assert not configure_telemetry("test-service", namespace)
    logger.info("private free-form content", extra={"event_name": "test.event"})

    captured = capsys.readouterr()
    events = [json.loads(line) for line in captured.err.splitlines()]
    assert [event["event"] for event in events] == [
        "telemetry.exporter.configuration_failed",
        "test.event",
    ]
    assert "collector credential" not in captured.err
    assert "private free-form content" not in captured.err

    for handler in tuple(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
