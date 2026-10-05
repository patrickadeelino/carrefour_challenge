from __future__ import annotations

import pytest

from carrefour_runtime.services.process.workflow_state import ProcessWorkflowState
from carrefour_runtime.value_objects.image_id import ImageId
from carrefour_runtime.value_objects.process_result import ProcessResult
from carrefour_runtime.value_objects.user_id import UserId


def make_state(
    names: tuple[str, ...] = ("Hemograma completo",),
) -> ProcessWorkflowState:
    state = ProcessWorkflowState(ImageId.new(), UserId("user-1"))
    state.record_ocr_result({"exams": list(names)})
    return state


def test_catalog_search_requires_the_exact_ocr_exam_list() -> None:
    state = make_state(("Hemograma completo", "Glicemia de jejum"))

    assert state.can_search_exams(["Hemograma completo", "Glicemia de jejum"])
    assert not state.can_search_exams(["Hemograma completo"])
    assert not state.can_search_exams(["CPF 123.456.789-00"])


def test_sensitive_data_review_blocks_catalog_and_appointment() -> None:
    state = ProcessWorkflowState(ImageId.new(), UserId("user-1"))
    state.record_ocr_result(
        {"status": "review_required", "reason": "sensitive_data_detected"}
    )

    assert not state.can_search_exams(["Hemograma completo"])
    assert state.resolved_exam_codes is None
    assert not state.can_schedule([])
    assert state.to_process_result().to_dict() == {
        "status": "review_required",
        "reason": "sensitive_data_detected",
    }


def test_unresolved_catalog_result_cannot_be_scheduled() -> None:
    state = make_state(("Hemograma completo", "Exame desconhecido"))
    names = ["Hemograma completo", "Exame desconhecido"]
    assert state.can_search_exams(names)
    state.record_catalog_result(
        {
            "results": [
                {
                    "input_indices": [0],
                    "status": "resolved",
                    "code": "CAT-001",
                    "canonical_name": "Hemograma completo",
                    "match_method": "canonical_exact",
                },
                {
                    "input_indices": [1],
                    "status": "not_found",
                    "match_method": "none",
                },
            ]
        }
    )

    assert state.resolved_exam_codes is None
    assert not state.can_schedule(["CAT-001"])
    assert state.to_process_result() == ProcessResult.catalog_review()


def test_only_all_verified_codes_can_be_scheduled() -> None:
    names = ("Hemograma completo", "Glicemia de jejum")
    state = make_state(names)
    state.record_catalog_result(
        {
            "results": [
                {
                    "input_indices": [0],
                    "status": "resolved",
                    "code": "CAT-001",
                    "canonical_name": "Hemograma completo",
                    "match_method": "canonical_exact",
                },
                {
                    "input_indices": [1],
                    "status": "resolved",
                    "code": "CAT-002",
                    "canonical_name": "Glicemia de jejum",
                    "match_method": "canonical_exact",
                },
            ]
        }
    )

    assert state.resolved_exam_codes == ("CAT-001", "CAT-002")
    assert state.can_schedule(["CAT-001", "CAT-002"])
    assert not state.can_schedule(["CAT-001"])
    assert not state.can_schedule(["CAT-001", "CAT-999"])


def test_workflow_result_contains_schedule_api_reconciliation() -> None:
    state = make_state(("Hemograma completo",))
    state.record_catalog_result(
        {
            "results": [
                {
                    "input_indices": [0],
                    "status": "resolved",
                    "code": "CAT-001",
                    "canonical_name": "Hemograma completo",
                    "match_method": "canonical_exact",
                }
            ]
        }
    )
    response = {
        "status": "completed",
        "already_scheduled": [],
        "newly_scheduled": [
            {
                "appointment_id": "75e39b6b-0ea7-4a4e-bbcc-20b137b1f70d",
                "scheduled_at": "2026-10-05T09:00:00-03:00",
                "exam_codes": ["CAT-001"],
            }
        ],
        "not_scheduled": [],
    }
    state.record_schedule_result(response)

    assert state.to_process_result().to_dict() == response


def test_empty_ocr_result_finishes_without_catalog_or_booking() -> None:
    state = make_state(())

    assert state.to_process_result().to_dict() == {"exams": []}


def test_catalog_can_group_duplicate_ocr_names_under_one_result() -> None:
    state = make_state(("Hemograma completo", "Hemograma completo"))
    state.record_catalog_result(
        {
            "results": [
                {
                    "input_indices": [0, 1],
                    "status": "resolved",
                    "code": "CAT-001",
                    "canonical_name": "Hemograma completo",
                    "match_method": "canonical_exact",
                }
            ]
        }
    )

    assert state.resolved_exam_codes == ("CAT-001",)
    assert state.can_schedule(["CAT-001"])
    assert state.resolved_exams() == [
        {
            "name": "Hemograma completo",
            "code": "CAT-001",
            "canonical_name": "Hemograma completo",
        },
        {
            "name": "Hemograma completo",
            "code": "CAT-001",
            "canonical_name": "Hemograma completo",
        },
    ]


@pytest.mark.parametrize(
    "results",
    [
        [],
        [
            {
                "input_indices": [0],
                "status": "resolved",
                "code": "CAT-001",
                "canonical_name": "Hemograma completo",
                "match_method": "canonical_exact",
            },
            {
                "input_indices": [0],
                "status": "resolved",
                "code": "CAT-001",
                "canonical_name": "Hemograma completo",
                "match_method": "canonical_exact",
            },
        ],
        [
            {
                "input_indices": [2],
                "status": "resolved",
                "code": "CAT-001",
                "canonical_name": "Hemograma completo",
                "match_method": "canonical_exact",
            },
            {
                "input_indices": [1],
                "status": "not_found",
                "match_method": "none",
            },
        ],
    ],
)
def test_catalog_response_must_cover_each_ocr_exam_once(results: list[dict]) -> None:
    state = make_state(("Hemograma completo", "Glicemia de jejum"))

    with pytest.raises(ValueError, match="catálogo.*inválido"):
        state.record_catalog_result({"results": results})
