import re
from dataclasses import dataclass
from typing import Literal

ExamMarkStatus = Literal["selected", "unselected", "ambiguous"]


@dataclass(frozen=True, slots=True)
class ExamCode:
    code: str
    left: int
    top: int

    def __post_init__(self) -> None:
        if re.fullmatch(r"EX-\d{3}", self.code) is None:
            raise ValueError("código de exame inválido")
        if self.left < 0 or self.top < 0:
            raise ValueError("posição do código de exame inválida")


@dataclass(frozen=True, slots=True)
class ExamMark:
    code: str
    name: str
    status: ExamMarkStatus
