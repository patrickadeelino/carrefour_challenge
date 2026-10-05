import json
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
from mcp import Client

from carrefour_ocr_mcp.contracts import ExamResult
from carrefour_ocr_mcp.server import create_server
from carrefour_ocr_mcp.services.exam_extractor.vision_exam_extractor import (
    VisionExamExtractor,
)


class FakeOcrProcessor:
    def __init__(self, result: ExamResult) -> None:
        self.result = result
        self.received_image: bytes | None = None

    async def extract_exams(self, image: bytes) -> ExamResult:
        self.received_image = image
        return self.result


@pytest.fixture
async def mcp_client(
    tmp_path: Path,
) -> AsyncIterator[tuple[Client, FakeOcrProcessor, bytes, str]]:
    image_id = str(uuid4())
    image = b"synthetic image bytes"
    (tmp_path / image_id).write_bytes(image)
    processor = FakeOcrProcessor({"exams": ["Hemograma completo"]})
    server = create_server(image_directory=tmp_path, ocr_processor=processor)

    async with Client(server) as client:
        yield client, processor, image, image_id


@pytest.mark.anyio
async def test_extract_exams_is_discoverable_and_processes_image_by_uuid(
    mcp_client: tuple[Client, FakeOcrProcessor, bytes, str],
    json_log_capture,
) -> None:
    client, processor, expected_image, image_id = mcp_client

    with json_log_capture("carrefour_ocr_mcp", "ocr-mcp") as log_stream:
        tools = await client.list_tools()
        result = await client.call_tool("extract_exams", {"image_id": image_id})

    assert [tool.name for tool in tools.tools] == ["extract_exams"]
    assert result.structured_content == {"exams": ["Hemograma completo"]}
    assert processor.received_image == expected_image
    records = [json.loads(line) for line in log_stream.getvalue().splitlines()]
    assert [record["event"] for record in records] == [
        "ocr.tool.started",
        "ocr.image.resolved",
        "ocr.tool.completed",
    ]
    assert records[1]["component"] == "image_access"
    assert records[2]["outcome"] == "success"
    assert image_id not in log_stream.getvalue()
    assert "Hemograma completo" not in log_stream.getvalue()


@pytest.mark.anyio
async def test_in_memory_transport_runs_extractor_with_mocked_vision(
    tmp_path: Path,
    numbered_vision_annotation: dict[str, object],
    numbered_request_image: bytes,
    vision_client_factory,
    json_log_capture,
) -> None:
    image_id = str(uuid4())
    (tmp_path / image_id).write_bytes(numbered_request_image)
    vision_client = vision_client_factory(numbered_vision_annotation)
    extractor = VisionExamExtractor(vision_client)
    server = create_server(image_directory=tmp_path, ocr_processor=extractor)

    with json_log_capture("carrefour_ocr_mcp", "ocr-mcp") as log_stream:
        async with Client(server) as client:
            result = await client.call_tool("extract_exams", {"image_id": image_id})

    assert result.structured_content == {
        "exams": [
            "Hemograma completo",
            "Glicemia de jejum",
            "Hemoglobina glicada (HbA1c)",
            "Colesterol total e frações",
            "TSH (hormônio tireoestimulante)",
        ]
    }
    assert vision_client.received_image == numbered_request_image
    records = [json.loads(line) for line in log_stream.getvalue().splitlines()]
    event_names = [record["event"] for record in records]
    assert "ocr.extraction.started" in event_names
    assert "ocr.extraction.completed" in event_names
    assert event_names[-1] == "ocr.tool.completed"
    assert records[-1]["outcome"] == "success"
    assert image_id not in log_stream.getvalue()
    assert "Hemograma completo" not in log_stream.getvalue()


@pytest.mark.anyio
async def test_extract_exams_rejects_non_uuid_without_reading_a_file(
    mcp_client: tuple[Client, FakeOcrProcessor, bytes, str],
    json_log_capture,
) -> None:
    client, processor, _, _ = mcp_client

    with json_log_capture("carrefour_ocr_mcp", "ocr-mcp") as log_stream:
        result = await client.call_tool("extract_exams", {"image_id": "../private"})

    assert result.is_error
    assert "../private" not in result.content[0].text
    assert processor.received_image is None
    record = json.loads(log_stream.getvalue().splitlines()[-1])
    assert record["event"] == "ocr.tool.rejected"
    assert record["level"] == "WARNING"
    assert record["component"] == "image_access"
    assert record["error_code"] == "invalid_image_id"
    assert "../private" not in log_stream.getvalue()


@pytest.mark.anyio
async def test_extract_exams_reports_missing_image_without_calling_processor(
    tmp_path: Path,
    json_log_capture,
) -> None:
    processor = FakeOcrProcessor({"exams": []})
    server = create_server(image_directory=tmp_path, ocr_processor=processor)

    image_id = str(uuid4())
    with json_log_capture("carrefour_ocr_mcp", "ocr-mcp") as log_stream:
        async with Client(server) as client:
            result = await client.call_tool("extract_exams", {"image_id": image_id})

    assert result.is_error
    assert "Imagem não encontrada" in result.content[0].text
    assert processor.received_image is None
    record = json.loads(log_stream.getvalue().splitlines()[-1])
    assert record["event"] == "ocr.tool.rejected"
    assert record["error_code"] == "image_not_found"
    assert image_id not in log_stream.getvalue()


@pytest.mark.anyio
async def test_extract_exams_preserves_manual_review_result_over_mcp(
    tmp_path: Path,
    json_log_capture,
) -> None:
    image_id = str(uuid4())
    (tmp_path / image_id).write_bytes(b"synthetic image bytes")
    processor = FakeOcrProcessor(
        {
            "status": "review_required",
            "exams": ["Hemograma completo"],
            "ambiguous_exams": ["Creatinina"],
        }
    )
    server = create_server(image_directory=tmp_path, ocr_processor=processor)

    with json_log_capture("carrefour_ocr_mcp", "ocr-mcp") as log_stream:
        async with Client(server) as client:
            result = await client.call_tool("extract_exams", {"image_id": image_id})

    assert result.structured_content == {
        "status": "review_required",
        "exams": ["Hemograma completo"],
        "ambiguous_exams": ["Creatinina"],
    }
    record = json.loads(log_stream.getvalue().splitlines()[-1])
    assert record["event"] == "ocr.tool.completed"
    assert record["level"] == "WARNING"
    assert record["outcome"] == "review_required"
    assert "Creatinina" not in log_stream.getvalue()


@pytest.mark.anyio
async def test_extract_exams_logs_sanitized_unexpected_failure(
    tmp_path: Path,
    json_log_capture,
) -> None:
    image_id = str(uuid4())
    (tmp_path / image_id).write_bytes(b"synthetic image bytes")

    class FailingProcessor:
        async def extract_exams(self, image: bytes) -> ExamResult:
            del image
            raise RuntimeError("synthetic private OCR payload")

    server = create_server(image_directory=tmp_path, ocr_processor=FailingProcessor())

    with json_log_capture("carrefour_ocr_mcp", "ocr-mcp") as log_stream:
        async with Client(server) as client:
            result = await client.call_tool("extract_exams", {"image_id": image_id})

    assert result.is_error
    record = json.loads(log_stream.getvalue().splitlines()[-1])
    assert record["event"] == "ocr.tool.failed"
    assert record["level"] == "ERROR"
    assert record["component"] == "exam_extractor"
    assert record["error_code"] == "ocr_extraction_failed"
    assert record["error_type"] == "RuntimeError"
    assert image_id not in log_stream.getvalue()
    assert "synthetic private OCR payload" not in log_stream.getvalue()
