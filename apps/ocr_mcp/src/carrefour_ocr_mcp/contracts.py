from typing import Literal, Protocol, TypeAlias, TypedDict


class ExamExtractionResult(TypedDict):
    exams: list[str]


class ExamReviewResult(TypedDict):
    status: Literal["review_required"]
    exams: list[str]
    ambiguous_exams: list[str]


ExamResult: TypeAlias = ExamExtractionResult | ExamReviewResult


class ExamExtractor(Protocol):
    async def extract_exams(self, image: bytes) -> ExamResult: ...
