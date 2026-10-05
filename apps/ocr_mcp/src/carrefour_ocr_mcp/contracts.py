from typing import Literal, Protocol, TypeAlias, TypedDict


class ExamExtractionResult(TypedDict):
    exams: list[str]


class ExamReviewResult(TypedDict):
    status: Literal["review_required"]
    exams: list[str]
    ambiguous_exams: list[str]


class ExamPiiReviewResult(TypedDict):
    status: Literal["review_required"]
    reason: Literal["sensitive_data_detected"]


ExamResult: TypeAlias = ExamExtractionResult | ExamReviewResult | ExamPiiReviewResult


class ExamExtractor(Protocol):
    async def extract_exams(self, image: bytes) -> ExamResult: ...
