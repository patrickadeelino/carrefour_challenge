import json
from pathlib import Path

import pytest

from carrefour_rag_mcp.catalog import CatalogLoader
from carrefour_rag_mcp.catalog.normalization import normalize_exam_name
from carrefour_rag_mcp.contracts import ResolvedExamResult, SearchExamsRequest
from carrefour_rag_mcp.services.exam_search import ExamSearchService

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"
EVALUATION_CASES = json.loads(
    (FIXTURES / "retrieval_cases.json").read_text(encoding="utf-8")
)
NORMALIZATION_CASES = tuple(
    (case["query"], case["expected_code"])
    for case in EVALUATION_CASES["normalized_exact"]
)

QUALIFIER_PAIRS = (
    ("T3 reverso", "T3 total"),
    ("T3 livre", "T3 total"),
    ("T4 livre", "T4 total"),
    ("IgG total", "IgM total"),
    ("Colesterol HDL", "Colesterol LDL"),
    ("Testosterona livre", "Testosterona total"),
    ("Glicemia de jejum", "Glicemia"),
    ("PSA livre", "PSA total"),
)


def test_every_canonical_name_and_alias_resolves_to_its_catalog_code() -> None:
    catalog = CatalogLoader.load_bundled()
    search = ExamSearchService(catalog)
    labels = [
        (
            label,
            exam.code,
            "canonical_exact"
            if normalize_exam_name(label) == normalize_exam_name(exam.name)
            else "alias_exact",
        )
        for exam in catalog.exams
        for label in (exam.name, *exam.aliases)
    ]

    assert len(catalog.exams) == 122
    assert sum(len(exam.aliases) for exam in catalog.exams) == 105
    assert len(labels) == 227

    for label, expected_code, expected_method in labels:
        response = search.search(SearchExamsRequest(exam_names=(label,)))

        assert len(response.results) == 1
        result = response.results[0]
        assert isinstance(result, ResolvedExamResult)
        assert result.code == expected_code
        assert result.match_method == expected_method


def test_exam_names_from_both_ocr_layouts_resolve_to_expected_codes() -> None:
    reference_cases = (
        ("Hemograma completo", "CAT-001"),
        ("Glicemia de jejum", "CAT-002"),
        ("Hemoglobina glicada (HbA1c)", "CAT-003"),
        ("Colesterol total e frações", "CAT-004"),
        ("TSH (hormônio tireoestimulante)", "CAT-005"),
        ("Hemograma completo", "CAT-001"),
        ("Glicemia de jejum", "CAT-002"),
        ("Hemoglobina glicada (HbA1c)", "CAT-003"),
        ("TSH", "CAT-005"),
        ("Colesterol LDL", "CAT-121"),
        ("Vitamina D (25-OH)", "CAT-024"),
    )
    search = ExamSearchService(CatalogLoader.load_bundled())

    assert len(reference_cases) == 11
    assert len({code for _, code in reference_cases}) == 7

    for name, expected_code in reference_cases:
        response = search.search(SearchExamsRequest(exam_names=(name,)))

        assert isinstance(response.results[0], ResolvedExamResult)
        assert response.results[0].code == expected_code


@pytest.mark.parametrize(("query", "expected_code"), NORMALIZATION_CASES)
def test_case_accent_punctuation_and_whitespace_variants_resolve_exactly(
    query: str,
    expected_code: str,
) -> None:
    search = ExamSearchService(CatalogLoader.load_bundled())

    response = search.search(SearchExamsRequest(exam_names=(query,)))

    assert isinstance(response.results[0], ResolvedExamResult)
    assert response.results[0].code == expected_code


@pytest.mark.parametrize(("first", "second"), QUALIFIER_PAIRS)
def test_normalization_preserves_clinically_meaningful_qualifiers(
    first: str,
    second: str,
) -> None:
    assert normalize_exam_name(first) != normalize_exam_name(second)


def test_shared_alias_returns_ambiguous_candidates_without_codes() -> None:
    catalog_json = json.dumps(
        {
            "exams": [
                {"code": "CAT-001", "name": "Exame alfa", "aliases": ["Painel"]},
                {"code": "CAT-002", "name": "Exame beta", "aliases": ["Painel"]},
            ]
        },
        ensure_ascii=False,
    )
    search = ExamSearchService(CatalogLoader.from_json(catalog_json))

    response = search.search(SearchExamsRequest(exam_names=("Painel",)))
    result = response.results[0]

    assert result.status == "ambiguous"
    assert tuple(candidate.canonical_name for candidate in result.candidates) == (
        "Exame alfa",
        "Exame beta",
    )
    assert all(not hasattr(candidate, "code") for candidate in result.candidates)


def test_equal_fuzzy_scores_use_catalog_code_as_stable_tie_breaker() -> None:
    catalog_json = json.dumps(
        {
            "exams": [
                {"code": "CAT-002", "name": "Hemograma A", "aliases": []},
                {"code": "CAT-001", "name": "Hemograma B", "aliases": []},
            ]
        },
        ensure_ascii=False,
    )
    search = ExamSearchService(CatalogLoader.from_json(catalog_json))
    request = SearchExamsRequest(exam_names=("Hemograma C",))

    first_response = search.search(request)
    repeated_response = search.search(request)

    first_result = first_response.results[0]
    repeated_result = repeated_response.results[0]
    assert first_result.status == "review_required"
    assert tuple(candidate.canonical_name for candidate in first_result.candidates) == (
        "Hemograma B",
        "Hemograma A",
    )
    assert first_result.model_dump() == repeated_result.model_dump()


def test_normalized_duplicates_keep_first_occurrence_order_and_all_indices() -> None:
    search = ExamSearchService(CatalogLoader.load_bundled())
    request = SearchExamsRequest(
        exam_names=("HbA1c", "  HBA1C ", "Glicemia-de-jejum", "HbA1c")
    )

    response = search.search(request)

    assert tuple(result.input_indices for result in response.results) == (
        (0, 1, 3),
        (2,),
    )
    assert tuple(result.canonical_name for result in response.results) == (
        "Hemoglobina glicada (HbA1c)",
        "Glicemia de jejum",
    )


def test_catalog_has_forty_labeled_retrieval_cases() -> None:
    assert sum(len(cases) for cases in EVALUATION_CASES.values()) == 40


def test_typo_cases_return_review_candidates_without_codes() -> None:
    catalog = CatalogLoader.load_bundled()
    search = ExamSearchService(catalog)
    canonical_name_by_code = {exam.code: exam.name for exam in catalog.exams}

    for case in EVALUATION_CASES["typo_candidates"]:
        response = search.search(SearchExamsRequest(exam_names=(case["query"],)))
        result = response.results[0]

        assert result.status == "review_required"
        assert len(result.candidates) <= 3
        assert canonical_name_by_code[case["expected_code"]] in {
            candidate.canonical_name for candidate in result.candidates
        }
        assert all(not hasattr(candidate, "code") for candidate in result.candidates)
        scores = [candidate.similarity for candidate in result.candidates]
        assert scores == sorted(scores, reverse=True)


def test_qualifier_near_misses_never_resolve_automatically() -> None:
    search = ExamSearchService(CatalogLoader.load_bundled())

    for case in EVALUATION_CASES["qualifier_near_misses"]:
        response = search.search(SearchExamsRequest(exam_names=(case["query"],)))

        assert response.results[0].status != "resolved"


def test_out_of_catalog_cases_are_not_found() -> None:
    search = ExamSearchService(CatalogLoader.load_bundled())

    for case in EVALUATION_CASES["out_of_catalog"]:
        response = search.search(SearchExamsRequest(exam_names=(case["query"],)))

        assert response.results[0].status == "not_found"


def test_search_does_not_log_names_or_queries(caplog: pytest.LogCaptureFixture) -> None:
    search = ExamSearchService(CatalogLoader.load_bundled())

    search.search(SearchExamsRequest(exam_names=("Hemograma completo",)))

    assert "Hemograma completo" not in caplog.text
