from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator, Mapping

from carrefour_ocr_mcp.services.exam_extractor.errors import ExamLayoutError
from carrefour_ocr_mcp.value_objects.bounding_box import BoundingBox
from carrefour_ocr_mcp.value_objects.ocr_document import OcrDocument, OcrWord


def parse_vision_document(annotation: Mapping[str, object]) -> OcrDocument:
    """Converte a resposta JSON do Vision para dados tipados usados pelos extratores."""
    full_text_annotation = as_mapping(annotation.get("fullTextAnnotation"))
    text = full_text_annotation.get("text") if full_text_annotation else None
    if not isinstance(text, str):
        raise ExamLayoutError("A resposta do OCR não contém texto estruturado.")

    pages = full_text_annotation.get("pages") if full_text_annotation else None
    return OcrDocument(text=text, paragraphs=_parse_paragraphs(pages))


def _parse_paragraphs(pages: object) -> tuple[tuple[OcrWord, ...], ...]:
    paragraphs: list[tuple[OcrWord, ...]] = []
    for paragraph in _iter_paragraphs(pages):
        words = paragraph.get("words")
        if not isinstance(words, list):
            continue
        paragraphs.append(
            tuple(
                parsed_word
                for value in words
                if (parsed_word := _parse_word(value)) is not None
            )
        )
    return tuple(paragraphs)


def _iter_paragraphs(pages: object) -> Iterator[Mapping[str, object]]:
    for page in _as_mappings(pages):
        for block in _as_mappings(page.get("blocks")):
            yield from _as_mappings(block.get("paragraphs"))


def _as_mappings(values: object) -> Iterator[Mapping[str, object]]:
    if not isinstance(values, list):
        return
    for value in values:
        mapping = as_mapping(value)
        if mapping is not None:
            yield mapping


def _parse_word(value: object) -> OcrWord | None:
    word = as_mapping(value)
    if word is None:
        return None
    return OcrWord(text=_word_text(word), bounds=_word_bounds(word))


def _word_text(word: Mapping[str, object]) -> str:
    symbols = word.get("symbols")
    if not isinstance(symbols, list):
        return ""
    return "".join(
        symbol_text
        for symbol in symbols
        if (symbol_mapping := as_mapping(symbol)) is not None
        and isinstance((symbol_text := symbol_mapping.get("text")), str)
    )


def _word_bounds(word: Mapping[str, object]) -> BoundingBox | None:
    bounding_box = as_mapping(word.get("boundingBox"))
    vertices = bounding_box.get("vertices") if bounding_box else None
    if not isinstance(vertices, list):
        return None

    points: list[tuple[int, int]] = []
    for value in vertices:
        vertex = as_mapping(value)
        if vertex is None:
            return None
        x = vertex.get("x", 0)
        y = vertex.get("y", 0)
        if not isinstance(x, int) or not isinstance(y, int):
            return None
        points.append((x, y))

    if len(points) < 4:
        return None
    if any(x < 0 or y < 0 for x, y in points):
        return None
    return BoundingBox(
        left=min(x for x, _ in points),
        top=min(y for _, y in points),
        right=max(x for x, _ in points),
        bottom=max(y for _, y in points),
    )


def as_mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def is_exam_code(value: str) -> bool:
    return re.fullmatch(r"EX-?\d{3}", value, flags=re.IGNORECASE) is not None


def fold_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return re.sub(r"\s+", " ", without_marks).upper()


def normalize_exam_name(value: str) -> str:
    value = re.sub(r"\s+([),.;])", r"\1", value)
    value = re.sub(r"([(])\s+", r"\1", value)
    return re.sub(r"\s*-\s*", "-", value).strip()
