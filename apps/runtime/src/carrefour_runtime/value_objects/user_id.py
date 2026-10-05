from __future__ import annotations

import re
from dataclasses import dataclass

_USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


@dataclass(frozen=True, slots=True)
class UserId:
    """Validated local identity used only to bind the scheduling request."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _USER_ID_PATTERN.fullmatch(
            self.value
        ):
            raise ValueError("identificador de usuário inválido")
