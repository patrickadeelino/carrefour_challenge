"""Strict request and response models for batched exam lookup."""

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SearchExamsRequest(StrictContractModel):
    exam_names: tuple[str, ...] = Field(min_length=1, max_length=50)

    @field_validator("exam_names")
    @classmethod
    def validate_exam_names(cls, exam_names: tuple[str, ...]) -> tuple[str, ...]:
        if any(not name.strip() for name in exam_names):
            raise ValueError("exam_names contém um valor vazio")
        if any(len(name) > 160 for name in exam_names):
            raise ValueError("exam_names contém um valor muito longo")
        if any(any(ord(character) < 32 for character in name) for name in exam_names):
            raise ValueError("exam_names contém caracteres de controle")
        return exam_names


class CatalogCandidate(StrictContractModel):
    canonical_name: str = Field(min_length=1, max_length=160)
    similarity: float | None = Field(default=None, ge=0, le=100)


class IndexedExamResult(StrictContractModel):
    input_indices: tuple[int, ...] = Field(min_length=1)

    @field_validator("input_indices")
    @classmethod
    def validate_input_indices(cls, indices: tuple[int, ...]) -> tuple[int, ...]:
        if any(index < 0 for index in indices):
            raise ValueError("input_indices contém posição negativa")
        if tuple(sorted(set(indices))) != indices:
            raise ValueError("input_indices deve ser único e crescente")
        return indices


class ResolvedExamResult(IndexedExamResult):
    status: Literal["resolved"]
    code: str = Field(pattern=r"^CAT-\d{3}$")
    canonical_name: str = Field(min_length=1, max_length=160)
    match_method: Literal["canonical_exact", "alias_exact"]


class AmbiguousExamResult(IndexedExamResult):
    status: Literal["ambiguous"]
    candidates: tuple[CatalogCandidate, ...] = Field(min_length=2)
    match_method: Literal["exact"]


class ReviewRequiredExamResult(IndexedExamResult):
    status: Literal["review_required"]
    candidates: tuple[CatalogCandidate, ...] = Field(min_length=1)
    match_method: Literal["fuzzy"]


class NotFoundExamResult(IndexedExamResult):
    status: Literal["not_found"]
    match_method: Literal["none"]


SearchExamResult: TypeAlias = Annotated[
    ResolvedExamResult
    | AmbiguousExamResult
    | ReviewRequiredExamResult
    | NotFoundExamResult,
    Field(discriminator="status"),
]


class SearchExamsResponse(StrictContractModel):
    results: tuple[SearchExamResult, ...]
