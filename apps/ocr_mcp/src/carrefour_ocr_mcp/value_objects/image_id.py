from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ImageId:
    """UUID canônico fornecido pelo runtime para localizar a imagem temporária."""

    value: UUID

    @classmethod
    def parse(cls, raw_value: str) -> ImageId:
        try:
            parsed_value = UUID(raw_value)
        except (AttributeError, ValueError) as error:
            raise ValueError("image_id deve ser um UUID canônico") from error

        if str(parsed_value) != raw_value:
            raise ValueError("image_id deve ser um UUID canônico")
        return cls(parsed_value)

    def __str__(self) -> str:
        return str(self.value)
