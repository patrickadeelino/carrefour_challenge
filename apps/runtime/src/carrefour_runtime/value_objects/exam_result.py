from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class ExamResult:
    """Resposta validada da extração de exames, pronta para serialização."""

    exams: tuple[str, ...]
    status: Literal["review_required"] | None = None
    ambiguous_exams: tuple[str, ...] = ()
    reason: Literal["sensitive_data_detected"] | None = None

    def __post_init__(self) -> None:
        names = (*self.exams, *self.ambiguous_exams)
        if any(not isinstance(name, str) or not name.strip() for name in names):
            raise ValueError("nom de exame não pode ser vazio")
        if self.status not in (None, "review_required"):
            raise ValueError("status de resultado de exame inválido")
        if self.status is None and self.ambiguous_exams:
            raise ValueError("exames ambíguos exigem revisão manual")
        if self.reason is not None and self.status != "review_required":
            raise ValueError("motivo de revisão exige status de revisão")
        if self.reason is not None and names:
            raise ValueError("revisão por dados sensíveis não pode expor exames")
        if (
            self.status == "review_required"
            and self.reason is None
            and not self.ambiguous_exams
        ):
            raise ValueError("revisão manual exige ao menos um exame ambíguo")

    @classmethod
    def from_mapping(cls, value: object) -> ExamResult:
        if not isinstance(value, Mapping):
            raise ValueError("OCR não retornou um resultado estruturado válido")

        if set(value) == {"exams"}:
            return cls(exams=_exam_names(value["exams"]))

        if set(value) == {"status", "exams", "ambiguous_exams"}:
            if value["status"] != "review_required":
                raise ValueError("OCR não retornou um resultado estruturado válido")
            return cls(
                exams=_exam_names(value["exams"]),
                status="review_required",
                ambiguous_exams=_exam_names(value["ambiguous_exams"]),
            )

        if (
            set(value) == {"status", "reason"}
            and value["status"] == "review_required"
            and value["reason"] == "sensitive_data_detected"
        ):
            return cls(
                exams=(),
                status="review_required",
                reason="sensitive_data_detected",
            )

        raise ValueError("OCR não retornou um resultado estruturado válido")

    @property
    def requires_review(self) -> bool:
        return self.status == "review_required"

    def to_dict(self) -> dict[str, object]:
        if not self.requires_review:
            return {"exams": list(self.exams)}
        if self.reason is not None:
            return {"status": "review_required", "reason": self.reason}
        return {
            "status": "review_required",
            "exams": list(self.exams),
            "ambiguous_exams": list(self.ambiguous_exams),
        }


def _exam_names(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("OCR não retornou um resultado estruturado válido")

    names: list[str] = []
    for name in value:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("OCR não retornou um resultado estruturado válido")
        names.append(name)
    return tuple(names)
