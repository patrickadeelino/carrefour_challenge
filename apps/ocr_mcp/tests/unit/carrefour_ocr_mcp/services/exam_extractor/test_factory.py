from io import BytesIO

import pytest
from PIL import Image

from carrefour_ocr_mcp.services.exam_extractor import (
    CheckboxExamExtractor,
    ExamExtractorFactory,
    ExamLayoutError,
    NumberedListExamExtractor,
)


def test_selects_checkbox_extractor_from_checkbox_layout_markers(
    checkbox_vision_annotation: dict[str, object], checkbox_image: Image.Image
) -> None:
    processor = ExamExtractorFactory().create(
        checkbox_vision_annotation, checkbox_image
    )

    assert isinstance(processor, CheckboxExamExtractor)


def test_selects_numbered_list_extractor_from_numbered_layout_markers(
    numbered_vision_annotation: dict[str, object], numbered_request_image: bytes
) -> None:
    with Image.open(BytesIO(numbered_request_image)) as source:
        image = source.convert("RGB")

    processor = ExamExtractorFactory().create(numbered_vision_annotation, image)

    assert isinstance(processor, NumberedListExamExtractor)


def test_unknown_layout_is_rejected_without_exposing_ocr_text() -> None:
    annotation = {"fullTextAnnotation": {"text": "PACIENTE TESTE 001"}}
    image = Image.new("RGB", (2, 2))

    with pytest.raises(ExamLayoutError) as error:
        ExamExtractorFactory().create(annotation, image)

    assert "PACIENTE TESTE" not in str(error.value)
