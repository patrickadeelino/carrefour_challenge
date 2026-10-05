from pathlib import Path
from uuid import uuid4

import pytest

from carrefour_ocr_mcp.contracts import ExamExtractionCandidate
from carrefour_ocr_mcp.services.exam_processing.errors import ExamProcessingError
from carrefour_ocr_mcp.services.exam_processing.service import ExamProcessingService
from carrefour_ocr_mcp.services.pii_guard import PiiOutputGuard


class FakeExtractor:
    def __init__(self, result: ExamExtractionCandidate) -> None:
        self.result = result
        self.received_image: bytes | None = None

    async def extract_exams(self, image: bytes) -> ExamExtractionCandidate:
        self.received_image = image
        return self.result


class NoPiiAnalyzer:
    def contains_pii(self, text: str) -> bool:
        del text
        return False


@pytest.mark.anyio
async def test_service_reads_by_uuid_extracts_and_applies_output_guard(
    tmp_path: Path,
) -> None:
    image_id = str(uuid4())
    image_bytes = b"synthetic image bytes"
    (tmp_path / image_id).write_bytes(image_bytes)
    extractor = FakeExtractor({"exams": ["Hemograma completo"]})
    service = ExamProcessingService(
        image_directory=tmp_path,
        extractor=extractor,
        pii_guard=PiiOutputGuard(NoPiiAnalyzer()),
    )

    result = await service.extract_exams(image_id)

    assert result == {"exams": ["Hemograma completo"]}
    assert extractor.received_image == image_bytes


@pytest.mark.anyio
async def test_service_normalizes_unexpected_extractor_failures_without_raw_message(
    tmp_path: Path,
) -> None:
    image_id = str(uuid4())
    (tmp_path / image_id).write_bytes(b"synthetic image bytes")

    class FailingExtractor:
        async def extract_exams(self, image: bytes) -> ExamExtractionCandidate:
            del image
            raise RuntimeError("SYNTHETIC_PRIVATE_OCR_CONTENT")

    service = ExamProcessingService(
        image_directory=tmp_path,
        extractor=FailingExtractor(),
        pii_guard=PiiOutputGuard(NoPiiAnalyzer()),
    )

    with pytest.raises(ExamProcessingError) as error:
        await service.extract_exams(image_id)

    assert error.value.error_code == "ocr_extraction_failed"
    assert error.value.component == "exam_extractor"
    assert error.value.error_type == "RuntimeError"
    assert "SYNTHETIC_PRIVATE_OCR_CONTENT" not in str(error.value)
