from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass

from carrefour_runtime.services.process.schedule_api_client import ScheduleApiResponse
from carrefour_runtime.value_objects.exam_result import ExamResult


@dataclass(frozen=True, slots=True)
class ProcessResult:
    """Validated CLI result and exit status for one processing workflow."""

    _payload: dict[str, object]
    exit_code: int
    schedule_response: ScheduleApiResponse | None = None
    _canonical_names_by_code: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.exit_code not in {0, 2}:
            raise ValueError("código de saída de processamento inválido")

    @classmethod
    def from_ocr(cls, value: object) -> ProcessResult:
        result = ExamResult.from_mapping(value)
        return cls(
            _payload=result.to_dict(),
            exit_code=2 if result.requires_review else 0,
        )

    @classmethod
    def catalog_review(cls) -> ProcessResult:
        return cls(
            _payload={"status": "review_required", "reason": "catalog_unresolved"},
            exit_code=2,
        )

    @classmethod
    def scheduled(
        cls,
        response: ScheduleApiResponse,
        canonical_names_by_code: Mapping[str, str],
    ) -> ProcessResult:
        return cls(
            _payload=response.to_dict(),
            exit_code=0,
            schedule_response=response,
            _canonical_names_by_code=tuple(canonical_names_by_code.items()),
        )

    @property
    def requires_review(self) -> bool:
        return self.exit_code == 2

    def to_dict(self) -> dict[str, object]:
        return deepcopy(self._payload)

    @property
    def canonical_names_by_code(self) -> dict[str, str]:
        return dict(self._canonical_names_by_code)
