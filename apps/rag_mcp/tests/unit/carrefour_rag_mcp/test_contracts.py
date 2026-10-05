import pytest
from pydantic import ValidationError

from carrefour_rag_mcp.contracts import (
    AmbiguousExamResult,
    ResolvedExamResult,
    ReviewRequiredExamResult,
    SearchExamsRequest,
    SearchExamsResponse,
)


def test_search_request_accepts_bounded_batch_without_echo_contract() -> None:
    request = SearchExamsRequest.model_validate_json(
        '{"exam_names": ["Hemograma", "TSH"]}'
    )

    assert request.exam_names == ("Hemograma", "TSH")


@pytest.mark.parametrize(
    "request_json",
    [
        '{"exam_names": []}',
        '{"exam_names": [""]}',
        '{"exam_names": ["   "]}',
        '{"exam_names": ["nome\\ncom controle"]}',
        '{"exam_names": ["' + "x" * 161 + '"]}',
        '{"exam_names": ["Hemograma"], "unexpected": true}',
    ],
)
def test_search_request_rejects_invalid_input(request_json: str) -> None:
    with pytest.raises(ValidationError):
        SearchExamsRequest.model_validate_json(request_json)


def test_search_request_limits_batch_to_fifty_names() -> None:
    names = ",".join('"Exame"' for _ in range(51))

    with pytest.raises(ValidationError):
        SearchExamsRequest.model_validate_json(f'{{"exam_names": [{names}]}}')


def test_contracts_keep_approximate_suggestions_out_of_resolved_code_field() -> None:
    result = SearchExamsResponse.model_validate_json(
        '{"results": [{"input_indices": [0, 2], "status": "review_required", '
        '"match_method": "fuzzy", "candidates": [{'
        '"canonical_name": "Hemograma completo", "similarity": 91.0}]}]}'
    )

    item = result.results[0]
    assert isinstance(item, ReviewRequiredExamResult)
    assert not isinstance(item, ResolvedExamResult)
    assert item.candidates[0].canonical_name == "Hemograma completo"
    assert item.input_indices == (0, 2)


def test_contracts_allow_ambiguous_candidates_without_selecting_one() -> None:
    result = SearchExamsResponse.model_validate_json(
        '{"results": [{"input_indices": [0], "status": "ambiguous", '
        '"match_method": "exact", "candidates": [{'
        '"canonical_name": "Exame A"}, {'
        '"canonical_name": "Exame B"}]}]}'
    )

    assert isinstance(result.results[0], AmbiguousExamResult)
    assert len(result.results[0].candidates) == 2


def test_resolved_contract_contains_only_selected_catalog_entry() -> None:
    resolved = ResolvedExamResult.model_validate_json(
        '{"input_indices": [0], "status": "resolved", "code": "CAT-001", '
        '"canonical_name": "Hemograma completo", '
        '"match_method": "canonical_exact"}'
    )

    assert resolved.code == "CAT-001"
    assert resolved.match_method == "canonical_exact"


def test_search_result_rejects_unsorted_or_repeated_input_indices() -> None:
    with pytest.raises(ValidationError):
        SearchExamsResponse.model_validate_json(
            '{"results": [{"input_indices": [2, 1], "status": "not_found", '
            '"match_method": "none"}]}'
        )


def test_candidate_contract_does_not_expose_a_code() -> None:
    with pytest.raises(ValidationError):
        SearchExamsResponse.model_validate_json(
            '{"results": [{"input_indices": [0], "status": "review_required", '
            '"match_method": "fuzzy", "candidates": [{"code": "CAT-001", '
            '"canonical_name": "Hemograma completo"}]}]}'
        )
