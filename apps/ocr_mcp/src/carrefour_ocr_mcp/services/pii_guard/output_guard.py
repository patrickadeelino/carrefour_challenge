from __future__ import annotations

from typing import Protocol, TypeGuard

from carrefour_ocr_mcp.contracts import (
    ExamExtractionCandidate,
    ExamPiiReviewResult,
    ExamResult,
    ExamReviewResult,
)
from carrefour_ocr_mcp.services.pii_guard.errors import (
    InvalidExamResultError,
    PiiAnalysisError,
)


class PiiTextAnalyzer(Protocol):
    def contains_pii(self, text: str) -> bool: ...


class PiiOutputGuard:
    """Prevent detected personal data from leaving the OCR service."""

    def __init__(self, analyzer: PiiTextAnalyzer) -> None:
        self._analyzer = analyzer

    def protect(self, result: ExamExtractionCandidate) -> ExamResult:
        safe_result, names = _validate_and_copy_result(result)
        try:
            contains_pii = False
            for name in names:
                contains_pii = self._analyzer.contains_pii(name) or contains_pii
        except Exception:
            raise PiiAnalysisError() from None

        if contains_pii:
            return ExamPiiReviewResult(
                status="review_required",
                reason="sensitive_data_detected",
            )

        return safe_result


def _validate_and_copy_result(
    result: object,
) -> tuple[ExamExtractionCandidate, tuple[str, ...]]:
    if not isinstance(result, dict):
        raise InvalidExamResultError()

    exam_names = result.get("exams")
    if not _is_string_list(exam_names):
        raise InvalidExamResultError()

    if set(result) == {"exams"}:
        copied_result: ExamExtractionCandidate = {"exams": list(exam_names)}
        return copied_result, tuple(exam_names)

    expected_review_fields = {"status", "exams", "ambiguous_exams"}
    ambiguous_names = result.get("ambiguous_exams")
    if (
        set(result) != expected_review_fields
        or result.get("status") != "review_required"
        or not _is_string_list(ambiguous_names)
    ):
        raise InvalidExamResultError()

    copied_review_result: ExamReviewResult = {
        "status": "review_required",
        "exams": list(exam_names),
        "ambiguous_exams": list(ambiguous_names),
    }
    return copied_review_result, (*exam_names, *ambiguous_names)


def _is_string_list(value: object) -> TypeGuard[list[str]]:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)
