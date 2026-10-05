import pytest

from carrefour_ocr_mcp.services.exam_extractor.errors import ExamLayoutError
from carrefour_ocr_mcp.services.exam_extractor.ocr_data import (
    fold_text,
    is_exam_code,
    normalize_exam_name,
    parse_vision_document,
)
from carrefour_ocr_mcp.value_objects.bounding_box import BoundingBox


@pytest.mark.parametrize(
    "annotation",
    [
        {},
        {"fullTextAnnotation": None},
        {"fullTextAnnotation": {"text": None}},
        {"fullTextAnnotation": {"text": 123}},
    ],
)
def test_parse_requires_structured_ocr_text(annotation: dict[str, object]) -> None:
    with pytest.raises(ExamLayoutError, match="não contém texto estruturado"):
        parse_vision_document(annotation)


def test_parse_joins_word_symbols_and_bounds_all_vertices() -> None:
    annotation: dict[str, object] = {
        "fullTextAnnotation": {
            "text": "Hemograma",
            "pages": [
                {
                    "blocks": [
                        {
                            "paragraphs": [
                                {
                                    "words": [
                                        {
                                            "symbols": [
                                                {"text": "Hemo"},
                                                {"text": "grama"},
                                                {"text": 7},
                                            ],
                                            "boundingBox": {
                                                "vertices": [
                                                    {"x": 8, "y": 4},
                                                    {"x": 12, "y": 2},
                                                    {"x": 16, "y": 5},
                                                    {"x": 7, "y": 9},
                                                ]
                                            },
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ],
        }
    }

    document = parse_vision_document(annotation)

    assert document.text == "Hemograma"
    assert list(document.iter_words())[0].text == "Hemograma"
    assert list(document.iter_words())[0].bounds == BoundingBox(7, 2, 16, 9)


def test_malformed_page_hierarchy_produces_no_paragraphs() -> None:
    document = parse_vision_document(
        {"fullTextAnnotation": {"text": "Texto OCR", "pages": "invalid"}}
    )

    assert document.paragraphs == ()


@pytest.mark.parametrize(
    "vertices",
    [
        "invalid",
        [{"x": 1, "y": 1}] * 3,
        [None, {"x": 1, "y": 1}, {"x": 2, "y": 2}, {"x": 3, "y": 3}],
        [
            {"x": -1, "y": 1},
            {"x": 1, "y": 1},
            {"x": 2, "y": 2},
            {"x": 3, "y": 3},
        ],
        [
            {"x": "invalid", "y": 1},
            {"x": 1, "y": 1},
            {"x": 2, "y": 2},
            {"x": 3, "y": 3},
        ],
    ],
)
def test_invalid_word_geometry_is_discarded(vertices: object) -> None:
    annotation: dict[str, object] = {
        "fullTextAnnotation": {
            "text": "Hemograma",
            "pages": [
                {
                    "blocks": [
                        {
                            "paragraphs": [
                                {
                                    "words": [
                                        {
                                            "symbols": [{"text": "H"}],
                                            "boundingBox": {"vertices": vertices},
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ],
        }
    }

    word = next(parse_vision_document(annotation).iter_words())

    assert word.text == "H"
    assert word.bounds is None


def test_word_without_symbols_is_kept_without_geometry() -> None:
    annotation: dict[str, object] = {
        "fullTextAnnotation": {
            "text": "Texto",
            "pages": [
                {"blocks": [{"paragraphs": [{"words": [{"symbols": "invalid"}]}]}]}
            ],
        }
    }

    word = next(parse_vision_document(annotation).iter_words())

    assert word.text == ""
    assert word.bounds is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [("EX123", True), ("ex-123", True), ("EX 123", False), ("EX-1234", False)],
)
def test_exam_code_recognition(value: str, expected: bool) -> None:
    assert is_exam_code(value) is expected


def test_fold_text_removes_accents_and_collapses_whitespace() -> None:
    assert fold_text(" Ácido   fólico ") == " ACIDO FOLICO "


def test_exam_name_normalization_repairs_spacing_around_punctuation() -> None:
    assert normalize_exam_name("Exame ( HbA1c ) - teste.") == "Exame (HbA1c)-teste."
