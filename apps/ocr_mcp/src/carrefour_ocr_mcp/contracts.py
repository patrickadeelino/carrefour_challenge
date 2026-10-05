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


ExamExtractionCandidate: TypeAlias = ExamExtractionResult | ExamReviewResult
ExamResult: TypeAlias = ExamExtractionCandidate | ExamPiiReviewResult


class ExamExtractor(Protocol):
    async def extract_exams(self, image: bytes) -> ExamExtractionCandidate: ...
