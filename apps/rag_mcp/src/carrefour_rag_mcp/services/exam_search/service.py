"""Resolve exam names against the approved catalog."""

from rapidfuzz import fuzz, process

from carrefour_rag_mcp.catalog.index import CatalogIndex
from carrefour_rag_mcp.catalog.models import CatalogDocument
from carrefour_rag_mcp.catalog.normalization import normalize_exam_name
from carrefour_rag_mcp.contracts import (
    AmbiguousExamResult,
    CatalogCandidate,
    NotFoundExamResult,
    ResolvedExamResult,
    ReviewRequiredExamResult,
    SearchExamResult,
    SearchExamsRequest,
    SearchExamsResponse,
)

FUZZY_REVIEW_THRESHOLD = 80.0
MAX_FUZZY_CANDIDATES = 3


class ExamSearchService:
    """Build an exact-match index and process bounded search batches."""

    def __init__(self, catalog: CatalogDocument) -> None:
        self._index = CatalogIndex(catalog)

    def search(self, request: SearchExamsRequest) -> SearchExamsResponse:
        input_indices_by_term: dict[str, list[int]] = {}
        for index, exam_name in enumerate(request.exam_names):
            normalized = normalize_exam_name(exam_name)
            input_indices_by_term.setdefault(normalized, []).append(index)

        results = tuple(
            self._search_term(normalized, tuple(input_indices))
            for normalized, input_indices in input_indices_by_term.items()
        )
        return SearchExamsResponse(results=results)

    def _search_term(
        self,
        normalized_term: str,
        input_indices: tuple[int, ...],
    ) -> SearchExamResult:
        matches = self._index.exact_matches(normalized_term)
        if len(matches) == 1:
            match = matches[0]
            return ResolvedExamResult(
                input_indices=input_indices,
                status="resolved",
                code=match.exam.code,
                canonical_name=match.exam.name,
                match_method=match.match_method,
            )

        if len(matches) > 1:
            return AmbiguousExamResult(
                input_indices=input_indices,
                status="ambiguous",
                candidates=tuple(
                    CatalogCandidate(canonical_name=match.exam.name)
                    for match in matches
                ),
                match_method="exact",
            )

        candidates = self._fuzzy_candidates(normalized_term)
        if not candidates:
            return self._not_found(input_indices)
        return ReviewRequiredExamResult(
            input_indices=input_indices,
            status="review_required",
            candidates=candidates,
            match_method="fuzzy",
        )

    def _fuzzy_candidates(
        self,
        normalized_term: str,
    ) -> tuple[CatalogCandidate, ...]:
        matches_by_code: dict[str, tuple[str, float]] = {}
        ranked_terms = process.extract(
            normalized_term,
            self._index.terms,
            scorer=fuzz.ratio,
            limit=None,
            score_cutoff=FUZZY_REVIEW_THRESHOLD,
        )
        for term, similarity, _index in ranked_terms:
            for match in self._index.exact_matches(term):
                current = matches_by_code.get(match.exam.code)
                if current is None or similarity > current[1]:
                    matches_by_code[match.exam.code] = (
                        match.exam.name,
                        similarity,
                    )

        candidates = sorted(
            matches_by_code.items(),
            key=lambda item: (-item[1][1], item[0]),
        )[:MAX_FUZZY_CANDIDATES]
        return tuple(
            CatalogCandidate(canonical_name=name, similarity=similarity)
            for _code, (name, similarity) in candidates
        )

    @staticmethod
    def _not_found(input_indices: tuple[int, ...]) -> SearchExamResult:
        return NotFoundExamResult(
            input_indices=input_indices,
            status="not_found",
            match_method="none",
        )
