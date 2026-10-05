from __future__ import annotations

from typing import cast

from PIL import Image

from carrefour_ocr_mcp.value_objects.exam import ExamCode, ExamMarkStatus

MIN_CHECKBOX_FRAME_SCORE = 0.15
DARK_PIXEL_THRESHOLD = 145
MIN_DIAGONAL_PIXELS = 28
CHECKBOX_X_OFFSET = 105
CHECKBOX_Y_OFFSET = 6
CHECKBOX_WIDTH = 80
CHECKBOX_HEIGHT = 82


class CheckboxMarkClassifier:
    """Classifica contorno e traços de um checkbox com pixels locais."""

    def __init__(self, image: Image.Image) -> None:
        self._image = image.convert("L")

    def classify(self, exam: ExamCode) -> ExamMarkStatus:
        region = self._checkbox_region(exam)
        if self._frame_score(region) < MIN_CHECKBOX_FRAME_SCORE:
            return "ambiguous"

        first_diagonal, second_diagonal = self._count_diagonal_ink(region)
        if (
            first_diagonal >= MIN_DIAGONAL_PIXELS
            and second_diagonal >= MIN_DIAGONAL_PIXELS
        ):
            return "selected"
        if (
            first_diagonal < MIN_DIAGONAL_PIXELS
            and second_diagonal < MIN_DIAGONAL_PIXELS
        ):
            return "unselected"
        return "ambiguous"

    def frame_score(self, exam: ExamCode) -> float:
        return self._frame_score(self._checkbox_region(exam))

    @staticmethod
    def _checkbox_region(exam: ExamCode) -> tuple[int, int, int, int]:
        left = exam.left - CHECKBOX_X_OFFSET
        top = exam.top + CHECKBOX_Y_OFFSET
        return left, top, left + CHECKBOX_WIDTH, top + CHECKBOX_HEIGHT

    def _frame_score(self, region: tuple[int, int, int, int]) -> float:
        left, top, right, bottom = region
        if (
            left < 0
            or top < 0
            or right > self._image.width
            or bottom > self._image.height
        ):
            return 0.0

        crop = self._image.crop(region)
        width, height = crop.size
        edge_depth = 10
        horizontal_start = width // 6
        horizontal_end = width - horizontal_start
        vertical_start = height // 6
        vertical_end = height - vertical_start

        def is_dark(x: int, y: int) -> bool:
            return cast(int, crop.getpixel((x, y))) < DARK_PIXEL_THRESHOLD

        edge_ratios = [
            sum(
                is_dark(x, y)
                for y in range(edge_depth)
                for x in range(horizontal_start, horizontal_end)
            )
            / ((horizontal_end - horizontal_start) * edge_depth),
            sum(
                is_dark(x, y)
                for y in range(height - edge_depth, height)
                for x in range(horizontal_start, horizontal_end)
            )
            / ((horizontal_end - horizontal_start) * edge_depth),
            sum(
                is_dark(x, y)
                for x in range(edge_depth)
                for y in range(vertical_start, vertical_end)
            )
            / (edge_depth * (vertical_end - vertical_start)),
            sum(
                is_dark(x, y)
                for x in range(width - edge_depth, width)
                for y in range(vertical_start, vertical_end)
            )
            / (edge_depth * (vertical_end - vertical_start)),
        ]
        return min(edge_ratios)

    def _count_diagonal_ink(self, region: tuple[int, int, int, int]) -> tuple[int, int]:
        crop = self._image.crop(region)
        width, height = crop.size
        first_diagonal = 0
        second_diagonal = 0
        margin_x = width // 4
        margin_y = height // 4
        for y in range(margin_y, height - margin_y):
            for x in range(margin_x, width - margin_x):
                if cast(int, crop.getpixel((x, y))) >= DARK_PIXEL_THRESHOLD:
                    continue
                if abs(y - x * height / width) <= 4:
                    first_diagonal += 1
                if abs(y - (width - 1 - x) * height / width) <= 4:
                    second_diagonal += 1
        return first_diagonal, second_diagonal
