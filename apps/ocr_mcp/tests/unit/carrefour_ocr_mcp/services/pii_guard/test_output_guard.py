from __future__ import annotations

from typing import Protocol

import pytest

from carrefour_ocr_mcp.contracts import ExamExtractionCandidate
from carrefour_ocr_mcp.services.pii_guard import (
    InvalidExamResultError,
    PiiAnalysisError,
    PiiOutputGuard,
)


class TextAnalyzer(Protocol):
    def contains_pii(self, text: str) -> bool: ...


class FakeTextAnalyzer:
    def __init__(self, sensitive_values: set[str]) -> None:
        self.sensitive_values = sensitive_values
        self.analyzed_values: list[str] = []

    def contains_pii(self, text: str) -> bool:
        self.analyzed_values.append(text)
        return text in self.sensitive_values


def test_keeps_exam_result_when_all_outbound_strings_are_safe() -> None:
    result: ExamExtractionCandidate = {
        "status": "review_required",
        "exams": ["Hemograma completo"],
        "ambiguous_exams": ["TSH"],
    }
    analyzer = FakeTextAnalyzer(set())

    protected_result = PiiOutputGuard(analyzer).protect(result)

    assert protected_result == result
    assert protected_result is not result
    assert analyzer.analyzed_values == ["Hemograma completo", "TSH"]


def test_rebuilds_success_result_using_only_the_allowed_fields() -> None:
    result: ExamExtractionCandidate = {"exams": ["Hemograma completo"]}

    protected_result = PiiOutputGuard(FakeTextAnalyzer(set())).protect(result)

    assert protected_result == {"exams": ["Hemograma completo"]}
    assert protected_result["exams"] is not result["exams"]


@pytest.mark.parametrize(
    "result",
    [
        {"exams": ["Hemograma completo"], "patient": "SYNTHETIC_PRIVATE"},
        {
            "status": "review_required",
            "reason": "sensitive_data_detected",
            "exams": ["SYNTHETIC_PRIVATE"],
        },
        {
            "status": "review_required",
            "exams": ["Hemograma completo"],
            "ambiguous_exams": ["TSH"],
            "patient": "SYNTHETIC_PRIVATE",
        },
    ],
)
def test_rejects_unexpected_fields_before_returning_any_result(
    result: ExamExtractionCandidate,
) -> None:
    with pytest.raises(InvalidExamResultError) as error:
        PiiOutputGuard(FakeTextAnalyzer(set())).protect(result)

    assert str(error.value) == "O OCR retornou um resultado fora do contrato permitido."
    assert "SYNTHETIC_PRIVATE" not in str(error.value)


@pytest.mark.parametrize(
    "result",
    [
        {"exams": ["Hemograma completo", 123]},
        {"exams": "Hemograma completo"},
        {"status": "partial", "exams": ["Hemograma completo"]},
        {"status": "review_required", "exams": ["TSH"]},
    ],
)
def test_rejects_malformed_result_shapes(
    result: ExamExtractionCandidate,
) -> None:
    with pytest.raises(InvalidExamResultError):
        PiiOutputGuard(FakeTextAnalyzer(set())).protect(result)


@pytest.mark.parametrize(
    "result",
    [
        {"exams": ["Hemograma completo", "CPF 123.456.789-00"]},
        {
            "status": "review_required",
            "exams": ["Hemograma completo"],
            "ambiguous_exams": ["CPF 123.456.789-00"],
        },
    ],
)
def test_suppresses_the_entire_result_when_any_outbound_string_has_pii(
    result: ExamExtractionCandidate,
) -> None:
    analyzer = FakeTextAnalyzer({"CPF 123.456.789-00"})

    protected_result = PiiOutputGuard(analyzer).protect(result)

    assert protected_result == {
        "status": "review_required",
        "reason": "sensitive_data_detected",
    }
    assert "123.456.789-00" not in str(protected_result)
    assert "Hemograma completo" not in str(protected_result)


def test_analyzes_every_outbound_string_before_returning_blocked_status() -> None:
    result: ExamExtractionCandidate = {
        "status": "review_required",
        "exams": ["CPF 123.456.789-00", "Hemograma completo"],
        "ambiguous_exams": ["TSH"],
    }
    analyzer = FakeTextAnalyzer({"CPF 123.456.789-00"})

    protected_result = PiiOutputGuard(analyzer).protect(result)

    assert protected_result == {
        "status": "review_required",
        "reason": "sensitive_data_detected",
    }
    assert analyzer.analyzed_values == [
        "CPF 123.456.789-00",
        "Hemograma completo",
        "TSH",
    ]


def test_does_not_return_exam_names_when_analysis_fails() -> None:
    sensitive_value = "CPF 123.456.789-00"

    class FailingAnalyzer:
        def contains_pii(self, text: str) -> bool:
            del text
            raise RuntimeError(sensitive_value)

    result: ExamExtractionCandidate = {"exams": [sensitive_value]}

    with pytest.raises(PiiAnalysisError) as error:
        PiiOutputGuard(FailingAnalyzer()).protect(result)

    assert str(error.value) == "Não foi possível verificar a privacidade do resultado."
    assert sensitive_value not in str(error.value)
