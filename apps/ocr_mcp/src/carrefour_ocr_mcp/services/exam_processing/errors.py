"""Sanitized failures from the OCR application service."""


class ExamProcessingError(RuntimeError):
    """Safe error details for adapters; never carries the original message."""

    def __init__(
        self,
        public_message: str,
        *,
        component: str,
        error_code: str,
        error_type: str,
        is_rejection: bool = False,
    ) -> None:
        super().__init__(public_message)
        self.public_message = public_message
        self.component = component
        self.error_code = error_code
        self.error_type = error_type
        self.is_rejection = is_rejection
