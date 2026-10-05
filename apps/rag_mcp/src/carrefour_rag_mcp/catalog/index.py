"""In-memory index from normalized catalog labels to exam records."""

from dataclasses import dataclass
from typing import Literal

from carrefour_rag_mcp.catalog.models import CatalogDocument, CatalogExam
from carrefour_rag_mcp.catalog.normalization import normalize_exam_name

ExactMatchMethod = Literal["canonical_exact", "alias_exact"]


@dataclass(frozen=True, slots=True)
class CatalogTermMatch:
    exam: CatalogExam
    match_method: ExactMatchMethod


class CatalogIndex:
    """Index canonical names and aliases without losing exact collisions."""

    def __init__(self, catalog: CatalogDocument) -> None:
        matches_by_term: dict[str, dict[str, CatalogTermMatch]] = {}
        for exam in catalog.exams:
            self._add(matches_by_term, exam.name, exam, "canonical_exact")
            for alias in exam.aliases:
                self._add(matches_by_term, alias, exam, "alias_exact")

        self._matches_by_term = {
            term: tuple(sorted(matches.values(), key=lambda match: match.exam.code))
            for term, matches in matches_by_term.items()
        }

    @staticmethod
    def _add(
        matches_by_term: dict[str, dict[str, CatalogTermMatch]],
        label: str,
        exam: CatalogExam,
        method: ExactMatchMethod,
    ) -> None:
        normalized = normalize_exam_name(label)
        matches = matches_by_term.setdefault(normalized, {})
        existing = matches.get(exam.code)
        if existing is None or method == "canonical_exact":
            matches[exam.code] = CatalogTermMatch(exam, method)

    def exact_matches(self, normalized_term: str) -> tuple[CatalogTermMatch, ...]:
        """Return all records for a key, ordered by stable catalog code."""
        return self._matches_by_term.get(normalized_term, ())

    @property
    def terms(self) -> tuple[str, ...]:
        """Return the distinct normalized keys used by the catalog."""
        return tuple(self._matches_by_term)
