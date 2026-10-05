import json
import os
import subprocess
import sys
import textwrap
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from mcp import Client

from carrefour_ocr_mcp.contracts import ExamExtractionCandidate
from carrefour_ocr_mcp.server import create_server
from carrefour_ocr_mcp.services.exam_extractor.vision_exam_extractor import (
    VisionExamExtractor,
)


class FakeOcrProcessor:
    def __init__(self, result: ExamExtractionCandidate) -> None:
        self.result = result
        self.received_image: bytes | None = None

    async def extract_exams(self, image: bytes) -> ExamExtractionCandidate:
        self.received_image = image
        return self.result


@pytest.fixture
async def mcp_client(
    tmp_path: Path,
    pii_output_guard,
) -> AsyncIterator[tuple[Client, FakeOcrProcessor, bytes, str]]:
    image_id = str(uuid4())
    image = b"synthetic image bytes"
    (tmp_path / image_id).write_bytes(image)
    processor = FakeOcrProcessor({"exams": ["Hemograma completo"]})
    server = create_server(
        image_directory=tmp_path,
        ocr_processor=processor,
        pii_guard=pii_output_guard,
    )

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
    pii_output_guard,
    json_log_capture,
) -> None:
    image_id = str(uuid4())
    (tmp_path / image_id).write_bytes(numbered_request_image)
    vision_client = vision_client_factory(numbered_vision_annotation)
    extractor = VisionExamExtractor(vision_client)
    server = create_server(
        image_directory=tmp_path,
        ocr_processor=extractor,
        pii_guard=pii_output_guard,
    )

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
@pytest.mark.parametrize(
    ("annotation_fixture", "image_fixture", "expected_exams"),
    [
        (
            "numbered_vision_annotation",
            "numbered_request_image",
            [
                "Hemograma completo",
                "Glicemia de jejum",
                "Hemoglobina glicada (HbA1c)",
                "Colesterol total e frações",
                "TSH (hormônio tireoestimulante)",
            ],
        ),
        (
            "checkbox_vision_annotation",
            "checkbox_request_image",
            [
                "Hemograma completo",
                "Glicemia de jejum",
                "Hemoglobina glicada (HbA1c)",
                "TSH",
                "Colesterol LDL",
                "Vitamina D (25-OH)",
            ],
        ),
    ],
    ids=["numbered-list", "checkbox-form"],
)
async def test_reference_layouts_pass_the_local_pii_boundary(
    tmp_path: Path,
    request: pytest.FixtureRequest,
    annotation_fixture: str,
    image_fixture: str,
    expected_exams: list[str],
    vision_client_factory,
    local_pii_output_guard,
) -> None:
    image_id = str(uuid4())
    image = request.getfixturevalue(image_fixture)
    (tmp_path / image_id).write_bytes(image)
    annotation: dict[str, Any] = request.getfixturevalue(annotation_fixture)
    extractor = VisionExamExtractor(vision_client_factory(annotation))
    server = create_server(
        image_directory=tmp_path,
        ocr_processor=extractor,
        pii_guard=local_pii_output_guard,
    )

    async with Client(server) as client:
        result = await client.call_tool("extract_exams", {"image_id": image_id})

    assert result.structured_content == {"exams": expected_exams}


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
    pii_output_guard,
    json_log_capture,
) -> None:
    processor = FakeOcrProcessor({"exams": []})
    server = create_server(
        image_directory=tmp_path,
        ocr_processor=processor,
        pii_guard=pii_output_guard,
    )

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
    pii_output_guard,
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
    server = create_server(
        image_directory=tmp_path,
        ocr_processor=processor,
        pii_guard=pii_output_guard,
    )

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
    pii_output_guard,
    json_log_capture,
) -> None:
    image_id = str(uuid4())
    (tmp_path / image_id).write_bytes(b"synthetic image bytes")

    class FailingProcessor:
        async def extract_exams(self, image: bytes) -> ExamExtractionCandidate:
            del image
            error = RuntimeError("synthetic private OCR payload")
            error.error_code = "SYNTHETIC_PRIVATE_ERROR_CODE"
            error.component = "SYNTHETIC_PRIVATE_COMPONENT"
            raise error

    server = create_server(
        image_directory=tmp_path,
        ocr_processor=FailingProcessor(),
        pii_guard=pii_output_guard,
    )
    with json_log_capture("carrefour_ocr_mcp", "ocr-mcp") as log_stream:
        async with Client(server) as client:
            result = await client.call_tool("extract_exams", {"image_id": image_id})

    assert result.is_error
    assert result.structured_content is None
    assert "synthetic private OCR payload" not in result.content[0].text
    record = json.loads(log_stream.getvalue().splitlines()[-1])
    assert record["event"] == "ocr.tool.failed"
    assert record["level"] == "ERROR"
    assert record["component"] == "exam_extractor"
    assert record["error_code"] == "ocr_extraction_failed"
    assert record["error_type"] == "RuntimeError"
    assert image_id not in log_stream.getvalue()
    assert "synthetic private OCR payload" not in log_stream.getvalue()
    assert "SYNTHETIC_PRIVATE_ERROR_CODE" not in log_stream.getvalue()
    assert "SYNTHETIC_PRIVATE_COMPONENT" not in log_stream.getvalue()


@pytest.mark.anyio
async def test_extract_exams_does_not_return_extra_fields_from_extractor(
    tmp_path: Path,
    pii_output_guard,
    json_log_capture,
) -> None:
    image_id = str(uuid4())
    (tmp_path / image_id).write_bytes(b"synthetic image bytes")
    sensitive_value = "SYNTHETIC_PRIVATE_PATIENT"
    processor = FakeOcrProcessor(
        cast(
            ExamExtractionCandidate,
            {"exams": ["Hemograma completo"], "patient": sensitive_value},
        )
    )
    server = create_server(
        image_directory=tmp_path,
        ocr_processor=processor,
        pii_guard=pii_output_guard,
    )
    with json_log_capture("carrefour_ocr_mcp", "ocr-mcp") as log_stream:
        async with Client(server) as client:
            result = await client.call_tool("extract_exams", {"image_id": image_id})

    assert result.is_error
    assert result.structured_content is None
    assert sensitive_value not in result.content[0].text
    assert sensitive_value not in log_stream.getvalue()
    records = [json.loads(line) for line in log_stream.getvalue().splitlines()]
    record = records[-1]
    assert record["event"] == "ocr.tool.failed"
    assert record["component"] == "pii_guard"
    assert record["error_code"] == "invalid_ocr_result"
    assert "SYNTHETIC_PRIVATE_ERROR_CODE" not in log_stream.getvalue()
    assert "SYNTHETIC_PRIVATE_COMPONENT" not in log_stream.getvalue()


def test_process_stderr_does_not_leak_unexpected_tool_exception(
    tmp_path: Path,
) -> None:
    app_root = Path(__file__).resolve().parents[3]
    private_marker = "SYNTHETIC_PRIVATE_OCR_EXCEPTION"
    script = textwrap.dedent(
        """
        import anyio
        import sys
        from pathlib import Path
        from uuid import uuid4

        from mcp import Client
        from carrefour_ocr_mcp.contracts import ExamExtractionCandidate
        from carrefour_ocr_mcp.server import create_server
        from carrefour_ocr_mcp.services.pii_guard import PiiOutputGuard

        class NoPiiAnalyzer:
            def contains_pii(self, text: str) -> bool:
                del text
                return False

        class FailingProcessor:
            async def extract_exams(self, image: bytes) -> ExamExtractionCandidate:
                del image
                error = RuntimeError("SYNTHETIC_PRIVATE_OCR_EXCEPTION")
                error.error_code = "SYNTHETIC_PRIVATE_ERROR_CODE"
                error.component = "SYNTHETIC_PRIVATE_COMPONENT"
                raise error

        async def main() -> None:
            directory = Path(sys.argv[1])
            image_id = str(uuid4())
            (directory / image_id).write_bytes(b"synthetic image bytes")
            server = create_server(
                image_directory=directory,
                ocr_processor=FailingProcessor(),
                pii_guard=PiiOutputGuard(NoPiiAnalyzer()),
            )
            async with Client(server) as client:
                result = await client.call_tool("extract_exams", {"image_id": image_id})
            print(f"RESULT_IS_ERROR={result.is_error}")

        anyio.run(main)
        """
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(app_root / "src"), environment.get("PYTHONPATH", "")])
    )

    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        capture_output=True,
        check=False,
        cwd=app_root,
        env=environment,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "RESULT_IS_ERROR=True"
    assert private_marker not in result.stdout
    assert private_marker not in result.stderr
    assert "SYNTHETIC_PRIVATE_ERROR_CODE" not in result.stderr
    assert "SYNTHETIC_PRIVATE_COMPONENT" not in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.anyio
async def test_extract_exams_suppresses_all_names_when_pii_is_found(
    tmp_path: Path,
    json_log_capture,
) -> None:
    from carrefour_ocr_mcp.services.pii_guard import PiiOutputGuard

    class MatchingPiiAnalyzer:
        def __init__(self, sensitive_value: str) -> None:
            self.sensitive_value = sensitive_value

        def contains_pii(self, text: str) -> bool:
            return text == self.sensitive_value

    image_id = str(uuid4())
    (tmp_path / image_id).write_bytes(b"synthetic image bytes")
    sensitive_value = "CPF 529.982.247-25"
    processor = FakeOcrProcessor({"exams": ["Hemograma completo", sensitive_value]})
    server = create_server(
        image_directory=tmp_path,
        ocr_processor=processor,
        pii_guard=PiiOutputGuard(MatchingPiiAnalyzer(sensitive_value)),
    )

    with json_log_capture("carrefour_ocr_mcp", "ocr-mcp") as log_stream:
        async with Client(server) as client:
            result = await client.call_tool("extract_exams", {"image_id": image_id})

    assert result.structured_content == {
        "status": "review_required",
        "reason": "sensitive_data_detected",
    }
    assert sensitive_value not in json.dumps(result.structured_content)
    assert "Hemograma completo" not in json.dumps(result.structured_content)
    assert sensitive_value not in log_stream.getvalue()
    records = [json.loads(line) for line in log_stream.getvalue().splitlines()]
    blocked = next(record for record in records if record["event"] == "ocr.pii.blocked")
    assert blocked["outcome"] == "review_required"
    assert blocked["error_code"] == "sensitive_data_detected"


@pytest.mark.anyio
async def test_extract_exams_fails_closed_when_pii_analysis_fails(
    tmp_path: Path,
    json_log_capture,
) -> None:
    from carrefour_ocr_mcp.services.pii_guard import PiiOutputGuard

    image_id = str(uuid4())
    (tmp_path / image_id).write_bytes(b"synthetic image bytes")
    sensitive_value = "CPF 529.982.247-25"

    class FailingPiiAnalyzer:
        def contains_pii(self, text: str) -> bool:
            del text
            raise RuntimeError(sensitive_value)

    processor = FakeOcrProcessor({"exams": [sensitive_value]})
    server = create_server(
        image_directory=tmp_path,
        ocr_processor=processor,
        pii_guard=PiiOutputGuard(FailingPiiAnalyzer()),
    )

    with json_log_capture("carrefour_ocr_mcp", "ocr-mcp") as log_stream:
        async with Client(server) as client:
            result = await client.call_tool("extract_exams", {"image_id": image_id})

    assert result.is_error
    assert sensitive_value not in result.content[0].text
    assert sensitive_value not in log_stream.getvalue()
    record = json.loads(log_stream.getvalue().splitlines()[-1])
    assert record["error_code"] == "pii_analysis_failed"
    assert record["component"] == "pii_guard"
