"""Trusted state and guards for the sequential OCR, catalog, and booking flow."""

from __future__ import annotations

import json
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from carrefour_runtime.services.process.schedule_api_client import (
    ScheduleApiResponse,
)
from carrefour_runtime.value_objects.exam_result import ExamResult
from carrefour_runtime.value_objects.image_id import ImageId
from carrefour_runtime.value_objects.process_result import ProcessResult
from carrefour_runtime.value_objects.user_id import UserId


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _CatalogCandidate(_StrictModel):
    canonical_name: str = Field(min_length=1, max_length=160)
    similarity: float | None = Field(default=None, ge=0, le=100)


class _IndexedExamResult(_StrictModel):
    input_indices: list[int] = Field(min_length=1)


class _ResolvedExamResult(_IndexedExamResult):
    status: Literal["resolved"]
    code: str = Field(pattern=r"^CAT-\d{3}$")
    canonical_name: str = Field(min_length=1, max_length=160)
    match_method: Literal["canonical_exact", "alias_exact"]


class _AmbiguousExamResult(_IndexedExamResult):
    status: Literal["ambiguous"]
    candidates: list[_CatalogCandidate] = Field(min_length=2)
    match_method: Literal["exact"]


class _ReviewRequiredExamResult(_IndexedExamResult):
    status: Literal["review_required"]
    candidates: list[_CatalogCandidate] = Field(min_length=1)
    match_method: Literal["fuzzy"]


class _NotFoundExamResult(_IndexedExamResult):
    status: Literal["not_found"]
    match_method: Literal["none"]


_SearchExamResult: TypeAlias = Annotated[
    _ResolvedExamResult
    | _AmbiguousExamResult
    | _ReviewRequiredExamResult
    | _NotFoundExamResult,
    Field(discriminator="status"),
]


class _CatalogSearchResponse(_StrictModel):
    results: list[_SearchExamResult]


class ProcessWorkflowState:
    """Keeps the tool results needed to authorize the next workflow step."""

    def __init__(self, image_id: ImageId, user_id: UserId) -> None:
        self.image_id = image_id
        self.user_id = user_id
        self.ocr_result: ExamResult | None = None
        self.catalog_result: _CatalogSearchResponse | None = None
        self._expanded_catalog_results: tuple[
            _ResolvedExamResult
            | _AmbiguousExamResult
            | _ReviewRequiredExamResult
            | _NotFoundExamResult,
            ...,
        ] = ()
        self.schedule_result: ScheduleApiResponse | None = None
        self.tool_rejection_code: str | None = None

    def before_tool(
        self, tool_name: str, arguments: dict[str, object]
    ) -> dict[str, str] | None:
        """Enforce the call order and bind tool arguments to trusted prior results."""
        if tool_name == "extract_exams":
            if arguments.get("image_id") == str(self.image_id):
                return None
            self.tool_rejection_code = "ocr_image_id_mismatch"
            return {"status": "rejected", "reason": "workflow_guard"}

        if tool_name == "search_exams":
            if self.can_search_exams(arguments.get("exam_names")):
                return None
            self.tool_rejection_code = "catalog_query_not_from_ocr"
            return {"status": "rejected", "reason": "workflow_guard"}

        if tool_name == "appointment_booking":
            if self.can_schedule(arguments.get("exam_codes")):
                return None
            self.tool_rejection_code = "unresolved_or_unverified_exam_codes"
            return {"status": "review_required", "reason": "catalog_unresolved"}

        return None

    def after_tool(
        self,
        tool_name: str,
        arguments: dict[str, object],
        response: object,
    ) -> None:
        """Record only structured responses emitted by the approved tools."""
        payload = _structured_payload(response)
        if tool_name == "extract_exams":
            self.record_ocr_result(payload)
            return
        if tool_name == "search_exams":
            if not self.can_search_exams(arguments.get("exam_names")):
                raise ValueError("consulta do catálogo não corresponde ao OCR")
            self.record_catalog_result(payload)
            return
        if tool_name == "appointment_booking":
            self.record_schedule_result(payload)

    def record_ocr_result(self, value: object) -> ExamResult:
        """Validate and store the exact structured result returned by OCR."""
        try:
            result = ExamResult.from_mapping(value)
        except ValueError:
            raise ValueError("resultado OCR inválido") from None
        self.ocr_result = result
        self.catalog_result = None
        self._expanded_catalog_results = ()
        return result

    def can_search_exams(self, exam_names: object) -> bool:
        """Permit only the complete exam list returned by a successful OCR call."""
        if self.ocr_result is None or self.ocr_result.requires_review:
            return False
        if not isinstance(exam_names, list):
            return False
        return tuple(exam_names) == self.ocr_result.exams

    def record_catalog_result(self, value: object) -> None:
        """Validate the RAG response and map each input index back to OCR order."""
        if self.ocr_result is None or self.ocr_result.requires_review:
            raise ValueError("resultado do catálogo inválido")

        try:
            response = _CatalogSearchResponse.model_validate(value)
            expanded = self._expand_results(response)
        except (ValidationError, ValueError):
            raise ValueError("resultado do catálogo inválido") from None

        self.catalog_result = response
        self._expanded_catalog_results = expanded

    def record_schedule_result(self, value: object) -> None:
        """Validate and store the API response used to build the CLI result."""
        if not self.can_schedule(list(self.resolved_exam_codes or ())):
            raise ValueError("agendamento fora da sequência aprovada")
        if isinstance(value, ScheduleApiResponse):
            self.schedule_result = value
            return
        try:
            result = ScheduleApiResponse.model_validate_json(json.dumps(value))
        except (TypeError, ValueError):
            raise ValueError("resposta da Schedule API inválida") from None
        self.schedule_result = result

    @property
    def resolved_exam_codes(self) -> tuple[str, ...] | None:
        """Return codes only when every OCR exam has one exact catalog match."""
        if not self._expanded_catalog_results:
            return None
        if any(
            result.status != "resolved" for result in self._expanded_catalog_results
        ):
            return None

        resolved = (
            result
            for result in self._expanded_catalog_results
            if isinstance(result, _ResolvedExamResult)
        )
        return tuple(dict.fromkeys(result.code for result in resolved))

    @property
    def requires_catalog_review(self) -> bool:
        return bool(self._expanded_catalog_results) and any(
            result.status != "resolved" for result in self._expanded_catalog_results
        )

    def can_schedule(self, exam_codes: object) -> bool:
        """Require the complete set of codes resolved for this OCR request."""
        expected_codes = self.resolved_exam_codes
        if expected_codes is None or not isinstance(exam_codes, list):
            return False
        if any(not isinstance(code, str) for code in exam_codes):
            return False
        return tuple(dict.fromkeys(exam_codes)) == expected_codes

    def resolved_exams(self) -> list[dict[str, str]]:
        """Build display records from OCR names and trusted exact catalog matches."""
        ocr_result = self.ocr_result
        if ocr_result is None or self.resolved_exam_codes is None:
            return []

        exams: list[dict[str, str]] = []
        for name, match in zip(
            ocr_result.exams, self._expanded_catalog_results, strict=True
        ):
            if isinstance(match, _ResolvedExamResult):
                exams.append(
                    {
                        "name": name,
                        "code": match.code,
                        "canonical_name": match.canonical_name,
                    }
                )
        return exams

    def unresolved_exams(self) -> list[dict[str, object]]:
        """Build review details without inventing a code for unresolved matches."""
        if self.ocr_result is None:
            return []

        unresolved: list[dict[str, object]] = []
        for name, match in zip(
            self.ocr_result.exams, self._expanded_catalog_results, strict=True
        ):
            if match.status == "resolved":
                continue
            candidates = getattr(match, "candidates", [])
            unresolved.append(
                {
                    "name": name,
                    "status": match.status,
                    "candidates": [
                        candidate.canonical_name for candidate in candidates
                    ],
                }
            )
        return unresolved

    def to_process_result(self) -> ProcessResult:
        """Build a CLI result only after a terminal workflow outcome exists."""
        ocr_result = self.ocr_result
        if ocr_result is None:
            raise ValueError("resultado OCR ausente")
        if ocr_result.requires_review or not ocr_result.exams:
            return ProcessResult.from_ocr(ocr_result.to_dict())
        if self.requires_catalog_review:
            return ProcessResult.catalog_review()
        if self.schedule_result is None:
            raise ValueError("resultado de agendamento ausente")
        canonical_names_by_code = {
            exam["code"]: exam["canonical_name"] for exam in self.resolved_exams()
        }
        return ProcessResult.scheduled(
            self.schedule_result,
            canonical_names_by_code,
        )

    def _expand_results(
        self, response: _CatalogSearchResponse
    ) -> tuple[
        _ResolvedExamResult
        | _AmbiguousExamResult
        | _ReviewRequiredExamResult
        | _NotFoundExamResult,
        ...,
    ]:
        if self.ocr_result is None:
            raise ValueError("OCR ausente")

        expanded: list[
            _ResolvedExamResult
            | _AmbiguousExamResult
            | _ReviewRequiredExamResult
            | _NotFoundExamResult
            | None
        ] = [None] * len(self.ocr_result.exams)
        for result in response.results:
            for input_index in result.input_indices:
                if input_index < 0 or input_index >= len(expanded):
                    raise ValueError("índice fora do intervalo")
                if expanded[input_index] is not None:
                    raise ValueError("índice duplicado")
                expanded[input_index] = result

        if any(result is None for result in expanded):
            raise ValueError("índice ausente")

        return tuple(result for result in expanded if result is not None)


def _structured_payload(value: object) -> object:
    if not isinstance(value, dict):
        return value
    if "structuredContent" in value:
        return value["structuredContent"]
    if "structured_content" in value:
        return value["structured_content"]
    return value
