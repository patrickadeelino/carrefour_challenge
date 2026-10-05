import json
from io import BytesIO

import pytest
from PIL import Image

from carrefour_ocr_mcp.services.exam_extractor import CheckboxExamExtractor
from carrefour_ocr_mcp.services.exam_extractor.ocr_data import parse_vision_document

EXPECTED_SELECTED_EXAMS = [
    "Hemograma completo",
    "Glicemia de jejum",
    "Hemoglobina glicada (HbA1c)",
    "TSH",
    "Colesterol LDL",
    "Vitamina D (25-OH)",
]


def test_extracts_only_x_marked_exams(
    caplog: pytest.LogCaptureFixture,
    checkbox_vision_annotation: dict[str, object],
    checkbox_image: Image.Image,
) -> None:
    full_text_annotation = checkbox_vision_annotation["fullTextAnnotation"]
    assert isinstance(full_text_annotation, dict)
    full_text = full_text_annotation["text"]
    assert isinstance(full_text, str)
    full_text_annotation["text"] = "PACIENTE TESTE 001\nCPF fictício\n" + full_text
    extractor = CheckboxExamExtractor(
        parse_vision_document(checkbox_vision_annotation), checkbox_image
    )

    result = extractor.extract_exams()

    assert result == {"exams": EXPECTED_SELECTED_EXAMS}
    assert "PACIENTE TESTE" not in json.dumps(result)
    assert "CPF fictício" not in json.dumps(result)
    assert "PACIENTE TESTE" not in caplog.text
    assert "CPF fictício" not in caplog.text


def test_requests_review_for_a_partial_checkbox_mark(
    checkbox_vision_annotation: dict[str, object], partial_mark_request_image: bytes
) -> None:
    with Image.open(BytesIO(partial_mark_request_image)) as source:
        image = source.convert("RGB")
    extractor = CheckboxExamExtractor(
        parse_vision_document(checkbox_vision_annotation), image
    )

    result = extractor.extract_exams()

    assert result == {
        "status": "review_required",
        "exams": EXPECTED_SELECTED_EXAMS,
        "ambiguous_exams": ["Creatinina"],
    }
