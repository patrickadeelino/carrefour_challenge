import pytest

from carrefour_ocr_mcp.services.exam_extractor import (
    ExamLayoutError,
    NumberedListExamExtractor,
)
from carrefour_ocr_mcp.services.exam_extractor.ocr_data import parse_vision_document

EXPECTED_EXAMS = [
    "Hemograma completo",
    "Glicemia de jejum",
    "Hemoglobina glicada (HbA1c)",
    "Colesterol total e frações",
    "TSH (hormônio tireoestimulante)",
]


def test_extracts_exams_from_numbered_list(
    numbered_vision_annotation: dict[str, object],
) -> None:
    extractor = NumberedListExamExtractor(
        parse_vision_document(numbered_vision_annotation).text
    )

    result = extractor.extract_exams()

    assert result == {"exams": EXPECTED_EXAMS}


def test_known_numbered_layout_with_no_exam_items_returns_empty_list() -> None:
    text = "EXAMES SOLICITADOS\nRealizar os exames abaixo:\nOBSERVAÇÃO"
    extractor = NumberedListExamExtractor(text)

    result = extractor.extract_exams()

    assert result == {"exams": []}


@pytest.mark.parametrize(
    ("text", "expected_message"),
    [
        ("Hemograma completo\nOBSERVAÇÃO", "lista de exames não foi localizada"),
        (
            "EXAMES SOLICITADOS\n1 Hemograma completo",
            "limite da lista de exames não foi reconhecido",
        ),
    ],
)
def test_rejects_missing_section_markers(text: str, expected_message: str) -> None:
    with pytest.raises(ExamLayoutError, match=expected_message):
        NumberedListExamExtractor(text).extract_exams()


@pytest.mark.parametrize(
    "numbered_items",
    [
        "1 Hemograma completo\n3 TSH",
        "1 Hemograma completo\n1 TSH",
        "2 Hemograma completo\n1 TSH",
    ],
)
def test_rejects_duplicate_or_non_sequential_item_numbers(
    numbered_items: str,
) -> None:
    text = f"EXAMES SOLICITADOS\n{numbered_items}\nOBSERVAÇÃO"

    with pytest.raises(ExamLayoutError, match="A lista de exames não pôde ser lida"):
        NumberedListExamExtractor(text).extract_exams()


def test_extracts_item_name_continued_on_the_next_line() -> None:
    text = "EXAMES SOLICITADOS\n1\nHemograma completo\nOBSERVAÇÃO"

    result = NumberedListExamExtractor(text).extract_exams()

    assert result == {"exams": ["Hemograma completo"]}


@pytest.mark.parametrize(
    "items",
    ["1", "1\n", "1\n2 Glicemia de jejum"],
)
def test_rejects_incomplete_numbered_item(items: str) -> None:
    text = f"EXAMES SOLICITADOS\n{items}\nOBSERVAÇÃO"

    with pytest.raises(ExamLayoutError, match="Um item da lista"):
        NumberedListExamExtractor(text).extract_exams()
