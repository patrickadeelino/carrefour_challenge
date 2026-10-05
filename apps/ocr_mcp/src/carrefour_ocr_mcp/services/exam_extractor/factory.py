from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from PIL import Image

from carrefour_ocr_mcp.contracts import ExamExtractionCandidate
from carrefour_ocr_mcp.services.exam_extractor.checkbox_extractor import (
    CheckboxExamExtractor,
)
from carrefour_ocr_mcp.services.exam_extractor.errors import ExamLayoutError
from carrefour_ocr_mcp.services.exam_extractor.numbered_list_extractor import (
    NumberedListExamExtractor,
)
from carrefour_ocr_mcp.services.exam_extractor.ocr_data import (
    fold_text,
    parse_vision_document,
)


class ExamProcessor(Protocol):
    def extract_exams(self) -> ExamExtractionCandidate: ...


class ExamExtractorFactory:
    """Select an extractor for one of the supported OCR layouts."""

    def create(
        self,
        annotation: Mapping[str, object],
        image: Image.Image,
    ) -> ExamProcessor:
        document = parse_vision_document(annotation)
        normalized_text = fold_text(document.text)

        if "MARQUE COM X OS EXAMES SOLICITADOS" in normalized_text:
            return CheckboxExamExtractor(document, image)

        if (
            "EXAMES SOLICITADOS" in normalized_text
            and "REALIZAR OS EXAMES ABAIXO" in normalized_text
        ):
            return NumberedListExamExtractor(document.text)

        raise ExamLayoutError("Não foi possível reconhecer o layout do pedido.")
