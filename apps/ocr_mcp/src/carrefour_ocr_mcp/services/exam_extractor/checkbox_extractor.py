from __future__ import annotations

import re

from PIL import Image

from carrefour_ocr_mcp.contracts import ExamResult
from carrefour_ocr_mcp.services.exam_extractor.checkbox_classifier import (
    CheckboxMarkClassifier,
)
from carrefour_ocr_mcp.services.exam_extractor.errors import ExamLayoutError
from carrefour_ocr_mcp.services.exam_extractor.ocr_data import (
    is_exam_code,
    normalize_exam_name,
)
from carrefour_ocr_mcp.value_objects.exam import (
    ExamCode,
    ExamMark,
)
from carrefour_ocr_mcp.value_objects.ocr_document import OcrDocument

EXPECTED_FORM_CODES = tuple(f"EX-{number}" for number in range(101, 111))


class CheckboxExamExtractor:
    """Resolve marked exams in the supported checkbox form using local pixels."""

    def __init__(self, document: OcrDocument, image: Image.Image) -> None:
        self._document = document
        self._image = image

    def extract_exams(self) -> ExamResult:
        return _extract_checkbox_exams(self._document, self._image)


def _extract_checkbox_exams(document: OcrDocument, image: Image.Image) -> ExamResult:
    classifier = CheckboxMarkClassifier(image)
    codes = _find_exam_codes(document, classifier)
    found_codes = {exam.code for exam in codes}
    if found_codes != set(EXPECTED_FORM_CODES):
        raise ExamLayoutError("Os itens do formulário não puderam ser identificados.")

    marks = [
        ExamMark(
            code=exam.code,
            name=_exam_name(document, exam),
            status=classifier.classify(exam),
        )
        for exam in sorted(codes, key=lambda exam: int(exam.code[-3:]))
    ]
    if any(not mark.name for mark in marks):
        raise ExamLayoutError("O nome de um exame não pôde ser identificado.")

    selected = [mark.name for mark in marks if mark.status == "selected"]
    ambiguous = [mark.name for mark in marks if mark.status == "ambiguous"]
    if ambiguous:
        return {
            "status": "review_required",
            "exams": selected,
            "ambiguous_exams": ambiguous,
        }
    return {"exams": selected}


def _find_exam_codes(
    document: OcrDocument, classifier: CheckboxMarkClassifier
) -> list[ExamCode]:
    candidates_by_code: dict[str, list[ExamCode]] = {}
    for words in document.paragraphs:
        normalized_characters: list[str] = []
        character_word_indexes: list[int] = []
        for word_index, word in enumerate(words):
            for character in word.text.upper():
                if character.isalnum():
                    normalized_characters.append(character)
                    character_word_indexes.append(word_index)

        normalized_text = "".join(normalized_characters)
        for match in re.finditer(r"EX\d{3}", normalized_text):
            word_indexes = sorted(
                {
                    character_word_indexes[position]
                    for position in range(match.start(), match.end())
                }
            )
            code_words = [words[word_index] for word_index in word_indexes]
            valid_bounds = [
                bounds for word in code_words if (bounds := word.bounds) is not None
            ]
            if not valid_bounds:
                continue

            code = f"EX-{match.group()[2:]}"
            exam = ExamCode(
                code=code,
                left=min(bound.left for bound in valid_bounds),
                top=min(bound.top for bound in valid_bounds),
            )
            candidates_by_code.setdefault(code, []).append(exam)

    return [
        max(
            candidates,
            key=classifier.frame_score,
        )
        for candidates in candidates_by_code.values()
    ]


def _exam_name(document: OcrDocument, exam: ExamCode) -> str:
    positioned_words: list[tuple[int, int, str]] = []
    for word in document.iter_words():
        text = word.text.strip()
        bounds = word.bounds
        if not text or bounds is None or is_exam_code(text):
            continue

        left = bounds.left
        center_y = bounds.center_y
        same_code_line = abs(center_y - exam.top) <= 20 and left >= exam.left + 65
        next_name_line = exam.top + 20 <= center_y <= exam.top + 100
        in_column = exam.left - 20 <= left <= exam.left + 550
        if in_column and (same_code_line or next_name_line):
            positioned_words.append((center_y, left, text))

    positioned_words.sort(key=lambda word: (word[1], word[0]))
    return normalize_exam_name(" ".join(text for _, _, text in positioned_words))
