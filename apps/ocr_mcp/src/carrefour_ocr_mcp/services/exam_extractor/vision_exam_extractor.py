from __future__ import annotations

import logging
from time import monotonic
from typing import Protocol

from carrefour_ocr_mcp.contracts import ExamResult
from carrefour_ocr_mcp.services.exam_extractor.factory import ExamExtractorFactory
from carrefour_ocr_mcp.services.exam_extractor.image_decoder import decode_image

logger = logging.getLogger(__name__)


class VisionAnnotationClient(Protocol):
    async def detect_document_text(self, image: bytes) -> dict[str, object]: ...


class VisionExamExtractor:
    """Obtain OCR data and delegate extraction to the layout-specific service."""

    def __init__(
        self,
        vision_client: VisionAnnotationClient,
        factory: ExamExtractorFactory | None = None,
    ) -> None:
        self._vision_client = vision_client
        self._factory = factory or ExamExtractorFactory()

    async def extract_exams(self, image: bytes) -> ExamResult:
        decoded_image = decode_image(image)
        annotation = await self._vision_client.detect_document_text(image)
        started_at = monotonic()
        logger.info(
            "ocr.extraction.started",
            extra={
                "event_name": "ocr.extraction.started",
                "component": "exam_extractor",
            },
        )
        processor = self._factory.create(annotation, decoded_image)
        result = processor.extract_exams()
        requires_review = result.get("status") == "review_required"
        log_completion = logger.warning if requires_review else logger.info
        log_completion(
            "ocr.extraction.completed",
            extra={
                "event_name": "ocr.extraction.completed",
                "component": "exam_extractor",
                "duration_ms": round((monotonic() - started_at) * 1000),
                "outcome": "review_required" if requires_review else "success",
            },
        )
        return result
