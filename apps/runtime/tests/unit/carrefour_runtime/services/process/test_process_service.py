from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from contextlib import contextmanager
from io import BytesIO, StringIO
from pathlib import Path
from uuid import UUID

import pytest
from carrefour_observability.logging_config import JsonEventFormatter
from PIL import Image

from carrefour_runtime.services.image_storage.temporary_store import (
    ImageStorageError,
    TemporaryImageStore,
)
from carrefour_runtime.services.process.errors import ProcessExecutionError
from carrefour_runtime.services.process.processing_lock import ProcessingLock
from carrefour_runtime.services.process.service import ProcessService
from carrefour_runtime.value_objects.image_id import ImageId
from carrefour_runtime.value_objects.process_result import ProcessResult


@contextmanager
def capture_process_logs():
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonEventFormatter("assistant-runtime"))
    logger = logging.getLogger("carrefour_runtime.services.process.service")
    previous_level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        yield stream
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        handler.close()


def make_png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (2, 2), color="white").save(output, format="PNG")
    return output.getvalue()


class FakeExecutor:
    def __init__(
        self,
        result: object | Exception,
        on_call: Callable[[ImageId], None] | None = None,
    ) -> None:
        self.result = result
        self.on_call = on_call
        self.received_image_id: ImageId | None = None

    async def execute(self, image_id: ImageId) -> object:
        self.received_image_id = image_id
        if self.on_call is not None:
            self.on_call(image_id)
        if isinstance(self.result, Exception):
            raise self.result
        if isinstance(self.result, dict):
            try:
                return ProcessResult.from_ocr(self.result)
            except ValueError:
                return self.result
        return self.result


@pytest.mark.parametrize(
    "result",
    [
        {"exams": ["Hemograma completo"]},
        {"exams": []},
        {
            "status": "review_required",
            "exams": ["Hemograma completo"],
            "ambiguous_exams": ["TSH"],
        },
        {
            "status": "review_required",
            "reason": "sensitive_data_detected",
        },
    ],
)
def test_process_stores_image_passes_only_uuid_and_deletes_temporary_copy(
    tmp_path: Path, result: dict[str, object]
) -> None:
    images = tmp_path / "input"
    images.mkdir()
    original = images / "request.png"
    original_bytes = make_png()
    original.write_bytes(original_bytes)
    store = TemporaryImageStore(tmp_path / "temporary")

    def verify_temporary_copy(image_id: ImageId) -> None:
        assert (store.root / str(image_id)).read_bytes() == original_bytes

    executor = FakeExecutor(
        result,
        on_call=verify_temporary_copy,
    )
    service = ProcessService(
        image_directory=images,
        image_store=store,
        executor=executor,
        lock_path=tmp_path / "locks" / "process.lock",
    )

    actual = asyncio.run(service.process("request.png"))

    assert actual.to_dict() == result
    assert executor.received_image_id is not None
    assert str(UUID(str(executor.received_image_id))) == str(executor.received_image_id)
    assert list(store.root.iterdir()) == []
    assert original.read_bytes() == original_bytes


def test_process_removes_image_when_workflow_fails_and_sanitizes_error(
    tmp_path: Path,
) -> None:
    images = tmp_path / "input"
    images.mkdir()
    (images / "request.png").write_bytes(make_png())
    store = TemporaryImageStore(tmp_path / "temporary")
    service = ProcessService(
        image_directory=images,
        image_store=store,
        executor=FakeExecutor(RuntimeError("patient name leaked")),
        lock_path=tmp_path / "locks" / "process.lock",
    )

    with pytest.raises(ProcessExecutionError, match="falha técnica") as error:
        asyncio.run(service.process("request.png"))

    assert "patient name" not in str(error.value)
    assert list(store.root.iterdir()) == []


def test_process_rejects_invalid_image_before_calling_workflow(tmp_path: Path) -> None:
    images = tmp_path / "input"
    images.mkdir()
    (images / "request.png").write_bytes(b"not a PNG image")
    store = TemporaryImageStore(tmp_path / "temporary")
    executor = FakeExecutor({"exams": []})
    service = ProcessService(
        image_directory=images,
        image_store=store,
        executor=executor,
        lock_path=tmp_path / "locks" / "process.lock",
    )

    with pytest.raises(ProcessExecutionError, match="imagem inválida"):
        asyncio.run(service.process("request.png"))

    assert executor.received_image_id is None
    assert list(store.root.iterdir()) == []


def test_process_reports_sanitized_failure_when_processing_and_cleanup_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    images = tmp_path / "input"
    images.mkdir()
    (images / "request.png").write_bytes(make_png())
    store = TemporaryImageStore(tmp_path / "temporary")

    def fail_cleanup(image_id: ImageId) -> bool:
        del image_id
        raise ImageStorageError("patient identifier leaked")

    monkeypatch.setattr(store, "delete", fail_cleanup)
    service = ProcessService(
        image_directory=images,
        image_store=store,
        executor=FakeExecutor(RuntimeError("patient name leaked")),
        lock_path=tmp_path / "locks" / "process.lock",
    )

    with pytest.raises(
        ProcessExecutionError, match="processamento e a limpeza"
    ) as error:
        asyncio.run(service.process("request.png"))

    assert "patient name" not in str(error.value)
    assert "patient identifier" not in str(error.value)
    assert len(list(store.root.iterdir())) == 1


@pytest.mark.parametrize(
    "malformed_result",
    [
        None,
        {"result": {"exams": []}},
        {"exams": "not a list"},
        {"status": "unknown"},
        {"status": "review_required", "exams": [], "ambiguous_exams": []},
        {
            "status": "review_required",
            "reason": "sensitive_data_detected",
            "exams": ["CPF 123.456.789-00"],
        },
    ],
)
def test_process_rejects_missing_or_malformed_workflow_result(
    tmp_path: Path, malformed_result: object
) -> None:
    images = tmp_path / "input"
    images.mkdir()
    (images / "request.png").write_bytes(make_png())
    store = TemporaryImageStore(tmp_path / "temporary")
    service = ProcessService(
        image_directory=images,
        image_store=store,
        executor=FakeExecutor(malformed_result),
        lock_path=tmp_path / "locks" / "process.lock",
    )

    with pytest.raises(ProcessExecutionError, match="resultado inválido"):
        asyncio.run(service.process("request.png"))

    assert list(store.root.iterdir()) == []


def test_process_logs_safe_lifecycle_events_and_stage_durations(tmp_path: Path) -> None:
    images = tmp_path / "input"
    images.mkdir()
    (images / "request.png").write_bytes(make_png())
    store = TemporaryImageStore(tmp_path / "temporary")
    service = ProcessService(
        image_directory=images,
        image_store=store,
        executor=FakeExecutor({"exams": ["Hemograma completo"]}),
        lock_path=tmp_path / "locks" / "process.lock",
    )

    with capture_process_logs() as log_stream:
        result = asyncio.run(service.process("request.png"))

    records = [json.loads(line) for line in log_stream.getvalue().splitlines()]
    events = [record["event"] for record in records]
    assert result.to_dict() == {"exams": ["Hemograma completo"]}
    assert events == [
        "process.started",
        "process.image.stored",
        "process.workflow.started",
        "process.workflow.completed",
        "process.image_cleanup.completed",
        "process.completed",
    ]
    assert records[1]["component"] == "temporary_image_store"
    assert records[1]["duration_ms"] >= 0
    assert records[3]["component"] == "workflow_executor"
    assert records[3]["duration_ms"] >= 0
    assert records[-1]["outcome"] == "success"
    serialized_logs = log_stream.getvalue()
    assert "Hemograma completo" not in serialized_logs
    assert "request.png" not in serialized_logs


def test_process_logs_input_rejection_with_stable_code(tmp_path: Path) -> None:
    service = ProcessService(
        image_directory=tmp_path / "missing-input",
        image_store=TemporaryImageStore(tmp_path / "temporary"),
        executor=FakeExecutor({"exams": []}),
        lock_path=tmp_path / "locks" / "process.lock",
    )

    with capture_process_logs() as log_stream, pytest.raises(ProcessExecutionError):
        asyncio.run(service.process("missing.png"))

    records = [json.loads(line) for line in log_stream.getvalue().splitlines()]
    failure = next(record for record in records if record["event"] == "process.failed")
    assert failure["level"] == "WARNING"
    assert failure["component"] == "input_reader"
    assert failure["error_code"] == "input_image_unavailable"
    assert failure["duration_ms"] >= 0


def test_process_logs_lock_rejection_without_reading_the_image(tmp_path: Path) -> None:
    lock_path = tmp_path / "locks" / "process.lock"
    service = ProcessService(
        image_directory=tmp_path / "missing-input",
        image_store=TemporaryImageStore(tmp_path / "temporary"),
        executor=FakeExecutor({"exams": []}),
        lock_path=lock_path,
    )

    with (
        capture_process_logs() as log_stream,
        ProcessingLock(lock_path),
        pytest.raises(ProcessExecutionError),
    ):
        asyncio.run(service.process("private-name.png"))

    records = [json.loads(line) for line in log_stream.getvalue().splitlines()]
    rejection = next(
        record for record in records if record["event"] == "process.lock.rejected"
    )
    assert rejection["level"] == "WARNING"
    assert rejection["component"] == "processing_lock"
    assert rejection["error_code"] == "process_already_running"
    assert "private-name.png" not in log_stream.getvalue()


def test_process_logs_cleanup_failure_without_exception_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    images = tmp_path / "input"
    images.mkdir()
    (images / "request.png").write_bytes(make_png())
    store = TemporaryImageStore(tmp_path / "temporary")

    def fail_cleanup(image_id: ImageId) -> bool:
        del image_id
        raise ImageStorageError("private patient filesystem marker")

    monkeypatch.setattr(store, "delete", fail_cleanup)
    service = ProcessService(
        image_directory=images,
        image_store=store,
        executor=FakeExecutor({"exams": []}),
        lock_path=tmp_path / "locks" / "process.lock",
    )

    with capture_process_logs() as log_stream, pytest.raises(ProcessExecutionError):
        asyncio.run(service.process("request.png"))

    records = [json.loads(line) for line in log_stream.getvalue().splitlines()]
    cleanup = next(
        record
        for record in records
        if record["event"] == "process.image_cleanup.failed"
    )
    assert cleanup["level"] == "ERROR"
    assert cleanup["component"] == "temporary_image_store"
    assert cleanup["error_code"] == "temporary_image_delete_failed"
    assert "private patient filesystem marker" not in log_stream.getvalue()
