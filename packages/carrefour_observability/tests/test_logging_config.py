import json
import logging

import pytest

from carrefour_observability.logging_config import (
    JsonEventFormatter,
    bind_request_id,
    configure_json_logging,
)


def test_formatter_adds_common_context_and_drops_unapproved_fields() -> None:
    record = logging.LogRecord(
        name="carrefour_observability.test",
        level=logging.WARNING,
        pathname="",
        lineno=0,
        msg="synthetic patient marker",
        args=(),
        exc_info=None,
    )
    record.event_name = "process.lock.rejected"
    record.component = "processing_lock"
    record.error_code = "process_already_running"
    record.patient_name = "synthetic private marker"

    payload = json.loads(JsonEventFormatter("assistant-runtime").format(record))

    assert payload == {
        "timestamp": payload["timestamp"],
        "level": "WARNING",
        "service": "assistant-runtime",
        "event": "process.lock.rejected",
        "component": "processing_lock",
        "error_code": "process_already_running",
    }
    assert payload["timestamp"].endswith("Z")
    assert "synthetic patient marker" not in json.dumps(payload)
    assert "synthetic private marker" not in json.dumps(payload)


def test_request_id_context_is_attached_to_records_and_reset_afterward() -> None:
    formatter = JsonEventFormatter("schedule-api")
    request_record = logging.LogRecord(
        name="carrefour_observability.test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="request started",
        args=(),
        exc_info=None,
    )
    request_record.event_name = "schedule.request.started"

    with bind_request_id("synthetic-request-id"):
        request_payload = json.loads(formatter.format(request_record))

    unrelated_record = logging.LogRecord(
        name="carrefour_observability.test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="startup event",
        args=(),
        exc_info=None,
    )
    unrelated_record.event_name = "schedule.database.ready"
    unrelated_payload = json.loads(formatter.format(unrelated_record))

    assert request_payload["request_id"] == "synthetic-request-id"
    assert "request_id" not in unrelated_payload


@pytest.mark.parametrize(
    "service_name", ["assistant-runtime", "ocr-mcp", "schedule-api"]
)
def test_configured_logger_emits_json_to_stderr_only(service_name: str, capsys) -> None:
    namespace = f"carrefour_observability.logging_test.{service_name}"
    configure_json_logging(namespace, service_name)
    logger = logging.getLogger(namespace)

    try:
        logger.info(
            "free-form content must be omitted",
            extra={"event_name": "test.event", "component": "test_component"},
        )

        captured = capsys.readouterr()
        payload = json.loads(captured.err)
        assert captured.out == ""
        assert payload["service"] == service_name
        assert payload["event"] == "test.event"
        assert payload["component"] == "test_component"
        assert "free-form content" not in captured.err
    finally:
        for handler in tuple(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
