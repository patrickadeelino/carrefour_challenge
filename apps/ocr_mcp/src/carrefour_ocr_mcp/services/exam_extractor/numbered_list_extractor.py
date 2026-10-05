from __future__ import annotations

import re

from carrefour_ocr_mcp.contracts import ExamResult
from carrefour_ocr_mcp.services.exam_extractor.errors import ExamLayoutError
from carrefour_ocr_mcp.services.exam_extractor.ocr_data import (
    normalize_exam_name,
)


class NumberedListExamExtractor:
    """Extract all exam names from the supported numbered-list layout."""

    def __init__(self, text: str) -> None:
        self._text = text

    def extract_exams(self) -> ExamResult:
        return {"exams": _extract_numbered_exams(self._text)}


def _extract_numbered_exams(full_text: str) -> list[str]:
    exam_lines = _numbered_exam_section(full_text)
    exams = _numbered_items(exam_lines)
    if not exams:
        return []

    positions = [position for position, _ in exams]
    if positions != list(range(1, len(exams) + 1)):
        raise ExamLayoutError("A lista de exames não pôde ser lida com segurança.")
    return [name for _, name in exams]


def _numbered_exam_section(full_text: str) -> list[str]:
    lines = full_text.splitlines()
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if "EXAMES SOLICITADOS" in line.upper()
        ),
        None,
    )
    if start is None:
        raise ExamLayoutError("A lista de exames não foi localizada no OCR.")

    end = next(
        (
            index
            for index, line in enumerate(lines[start + 1 :], start + 1)
            if "OBSERVA" in line.upper()
        ),
        None,
    )
    if end is None:
        raise ExamLayoutError("O limite da lista de exames não foi reconhecido.")

    return lines[start + 1 : end]


def _numbered_items(lines: list[str]) -> list[tuple[int, str]]:
    exams: list[tuple[int, str]] = []
    index = 0
    while index < len(lines):
        item = _numbered_item(lines, index)
        if item is None:
            index += 1
            continue
        exam, index = item
        exams.append((exam[0], normalize_exam_name(exam[1])))
    return exams


def _numbered_item(lines: list[str], index: int) -> tuple[tuple[int, str], int] | None:
    match = re.match(r"^\s*(\d{1,2})[.)]?\s*(.*?)\s*$", lines[index])
    if match is None:
        return None

    name = match.group(2).strip()
    next_index = index + 1
    if not name:
        if next_index >= len(lines):
            raise ExamLayoutError("Um item da lista não pôde ser lido com segurança.")
        name = lines[next_index].strip()
        if not name or re.match(r"^\s*\d", name):
            raise ExamLayoutError("Um item da lista não pôde ser lido com segurança.")
        next_index += 1
    return (int(match.group(1)), name), next_index
