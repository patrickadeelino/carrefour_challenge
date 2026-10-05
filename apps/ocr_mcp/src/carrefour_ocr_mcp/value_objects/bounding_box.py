from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BoundingBox:
    left: int
    top: int
    right: int
    bottom: int

    def __post_init__(self) -> None:
        if self.left < 0 or self.top < 0:
            raise ValueError(
                "coordenadas da caixa delimitadora não podem ser negativas"
            )
        if self.right < self.left or self.bottom < self.top:
            raise ValueError("limites da caixa delimitadora estão invertidos")

    @property
    def center_y(self) -> int:
        return (self.top + self.bottom) // 2
