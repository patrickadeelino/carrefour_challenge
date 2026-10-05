from collections.abc import Iterator
from dataclasses import dataclass

from carrefour_ocr_mcp.value_objects.bounding_box import BoundingBox


@dataclass(frozen=True, slots=True)
class OcrWord:
    text: str
    bounds: BoundingBox | None


@dataclass(frozen=True, slots=True)
class OcrDocument:
    text: str
    paragraphs: tuple[tuple[OcrWord, ...], ...]

    def iter_words(self) -> Iterator[OcrWord]:
        for paragraph in self.paragraphs:
            yield from paragraph
