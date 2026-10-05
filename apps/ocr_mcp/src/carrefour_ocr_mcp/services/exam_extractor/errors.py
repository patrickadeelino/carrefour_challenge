class ExamLayoutError(ValueError):
    """OCR data does not match one of the supported exam request layouts."""

    error_code = "exam_layout_unrecognized"
    component = "exam_extractor"


class ExamImageError(ValueError):
    """Image bytes cannot be decoded for local checkbox analysis."""

    error_code = "image_decode_failed"
    component = "exam_extractor"
