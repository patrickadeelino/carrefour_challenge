"""Coordinate image access, exam extraction, and the outbound PII barrier."""

from __future__ import annotations

import logging
from pathlib import Path
from time import monotonic

from carrefour_ocr_mcp.contracts import ExamExtractor, ExamResult
from carrefour_ocr_mcp.image_access import ImageAccessError, read_image
from carrefour_ocr_mcp.services.exam_extractor.errors import (
    ExamImageError,
    ExamLayoutError,
)
from carrefour_ocr_mcp.services.exam_processing.errors import ExamProcessingError
from carrefour_ocr_mcp.services.pii_guard import PiiOutputGuard
from carrefour_ocr_mcp.services.pii_guard.errors import (
    InvalidExamResultError,
    PiiAnalysisError,
)
from carrefour_ocr_mcp.vision_client import (
    VisionApiError,
    VisionClientError,
    VisionConfigurationError,
    VisionConnectionError,
    VisionResponseError,
    VisionTimeoutError,
)

logger = logging.getLogger(__name__)
GENERIC_TOOL_FAILURE_MESSAGE = "Não foi possível processar a imagem."
_IMAGE_ACCESS_MESSAGES = {
    "invalid_image_id": "image_id deve ser um UUID válido.",
    "image_not_found": "Imagem não encontrada.",
    "image_unavailable": "Imagem indisponível.",
    "image_access_failed": "Não foi possível acessar a imagem.",
}
_IMAGE_ACCESS_REJECTIONS = frozenset(
    {"invalid_image_id", "image_not_found", "image_unavailable"}
)
_ERROR_CLASSIFICATIONS: dict[type[Exception], tuple[str, str]] = {
    InvalidExamResultError: ("pii_guard", "invalid_ocr_result"),
    PiiAnalysisError: ("pii_guard", "pii_analysis_failed"),
    ExamImageError: ("exam_extractor", "image_decode_failed"),
    ExamLayoutError: ("exam_extractor", "exam_layout_unrecognized"),
    VisionConfigurationError: ("vision_client", "vision_configuration_invalid"),
    VisionTimeoutError: ("vision_client", "vision_timeout"),
    VisionConnectionError: ("vision_client", "vision_connection_failed"),
    VisionApiError: ("vision_client", "vision_api_rejected"),
    VisionResponseError: ("vision_client", "vision_invalid_response"),
    VisionClientError: ("vision_client", "vision_client_failed"),
}


class ExamProcessingService:
    """Run OCR for an internal image ID and protect every outbound exam name."""

    def __init__(
        self,
        image_directory: Path,
        extractor: ExamExtractor,
        pii_guard: PiiOutputGuard,
    ) -> None:
        self._image_directory = image_directory
        self._extractor = extractor
        self._pii_guard = pii_guard

    async def extract_exams(self, image_id: str) -> ExamResult:
        image_started_at = monotonic()
        try:
            image = read_image(self._image_directory, image_id)
        except Exception as error:
            raise _processing_error(error) from None

        logger.info(
            "ocr.image.resolved",
            extra={
                "event_name": "ocr.image.resolved",
                "component": "image_access",
                "duration_ms": _duration_ms(image_started_at),
            },
        )

        try:
            candidate = await self._extractor.extract_exams(image)
            result = self._pii_guard.protect(candidate)
        except Exception as error:
            raise _processing_error(error) from None

        if result.get("reason") == "sensitive_data_detected":
            logger.warning(
                "ocr.pii.blocked",
                extra={
                    "event_name": "ocr.pii.blocked",
                    "component": "pii_guard",
                    "error_code": "sensitive_data_detected",
                    "outcome": "review_required",
                },
            )

        return result


def _processing_error(error: Exception) -> ExamProcessingError:
    if isinstance(error, ImageAccessError):
        component, error_code = "image_access", error.error_code
        public_message = _IMAGE_ACCESS_MESSAGES.get(
            error_code, GENERIC_TOOL_FAILURE_MESSAGE
        )
        return ExamProcessingError(
            public_message,
            component=component,
            error_code=error_code
            if error_code in _IMAGE_ACCESS_MESSAGES
            else "image_access_failed",
            error_type=type(error).__name__,
            is_rejection=error_code in _IMAGE_ACCESS_REJECTIONS,
        )

    for error_type, (component, error_code) in _ERROR_CLASSIFICATIONS.items():
        if isinstance(error, error_type):
            return ExamProcessingError(
                GENERIC_TOOL_FAILURE_MESSAGE,
                component=component,
                error_code=error_code,
                error_type=type(error).__name__,
            )

    return ExamProcessingError(
        GENERIC_TOOL_FAILURE_MESSAGE,
        component="exam_extractor",
        error_code="ocr_extraction_failed",
        error_type=type(error).__name__,
    )


def _duration_ms(started_at: float) -> int:
    return round((monotonic() - started_at) * 1000)
