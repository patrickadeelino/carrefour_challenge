from __future__ import annotations

from typing import Protocol, cast

from carrefour_ocr_mcp.contracts import (
    ExamPiiReviewResult,
    ExamResult,
    ExamReviewResult,
)
from carrefour_ocr_mcp.services.pii_guard.errors import PiiAnalysisError


class PiiTextAnalyzer(Protocol):
    def contains_pii(self, text: str) -> bool: ...


class PiiOutputGuard:
    """Prevent detected personal data from leaving the OCR service."""

    def __init__(self, analyzer: PiiTextAnalyzer) -> None:
        self._analyzer = analyzer

    def protect(self, result: ExamResult) -> ExamResult:
        try:
            contains_pii = False
            for name in _result_names(result):
                contains_pii = self._analyzer.contains_pii(name) or contains_pii
        except Exception:
            raise PiiAnalysisError() from None

        if contains_pii:
            return ExamPiiReviewResult(
                status="review_required",
                reason="sensitive_data_detected",
            )

        return result


def _result_names(result: ExamResult) -> tuple[str, ...]:
    if "reason" in result:
        return ()

    exam_names = tuple(result["exams"])
    if "ambiguous_exams" not in result:
        return exam_names

    review_result = cast(ExamReviewResult, result)
    return (*exam_names, *review_result["ambiguous_exams"])
