from __future__ import annotations

from carrefour_runtime.value_objects.process_result import ProcessResult


def test_process_result_preserves_valid_empty_ocr_result() -> None:
    result = ProcessResult.from_ocr({"exams": []})

    assert result.to_dict() == {"exams": []}
    assert result.exit_code == 0


def test_process_result_uses_review_exit_code_for_manual_review() -> None:
    result = ProcessResult.from_ocr(
        {
            "status": "review_required",
            "reason": "sensitive_data_detected",
        }
    )

    assert result.to_dict() == {
        "status": "review_required",
        "reason": "sensitive_data_detected",
    }
    assert result.exit_code == 2


def test_process_result_reports_catalog_review_without_ocr_content() -> None:
    result = ProcessResult.catalog_review()

    assert result.to_dict() == {
        "status": "review_required",
        "reason": "catalog_unresolved",
    }
    assert result.exit_code == 2
