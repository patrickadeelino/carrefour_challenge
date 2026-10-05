import logging
from pathlib import Path
from time import monotonic

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

from carrefour_ocr_mcp.contracts import ExamExtractor, ExamResult
from carrefour_ocr_mcp.image_access import ImageAccessError, read_image
from carrefour_ocr_mcp.services.pii_guard import PiiOutputGuard

logger = logging.getLogger(__name__)


def create_server(
    image_directory: Path,
    ocr_processor: ExamExtractor,
    pii_guard: PiiOutputGuard,
) -> MCPServer:
    server = MCPServer("carrefour-ocr")

    @server.tool()
    async def extract_exams(image_id: str) -> dict[str, object]:
        """Identifica os exames presentes em uma imagem temporária pelo UUID."""
        started_at = monotonic()
        logger.info(
            "ocr.tool.started",
            extra={
                "event_name": "ocr.tool.started",
                "component": "mcp_tool",
            },
        )
        try:
            image_started_at = monotonic()
            image = read_image(image_directory, image_id)
            logger.info(
                "ocr.image.resolved",
                extra={
                    "event_name": "ocr.image.resolved",
                    "component": "image_access",
                    "duration_ms": _duration_ms(image_started_at),
                },
            )
            raw_result: ExamResult = await ocr_processor.extract_exams(image)
            result = pii_guard.protect(raw_result)
        except Exception as error:
            error_code = getattr(error, "error_code", "ocr_extraction_failed")
            is_rejection = isinstance(error, ImageAccessError) and error_code in {
                "invalid_image_id",
                "image_not_found",
                "image_unavailable",
            }
            log_failure = logger.warning if is_rejection else logger.error
            event_name = "ocr.tool.rejected" if is_rejection else "ocr.tool.failed"
            log_failure(
                event_name,
                extra={
                    "event_name": event_name,
                    "component": getattr(error, "component", "exam_extractor"),
                    "duration_ms": _duration_ms(started_at),
                    "error_code": error_code,
                    "error_type": type(error).__name__,
                },
            )
            raise

        pii_blocked = result.get("reason") == "sensitive_data_detected"
        if pii_blocked:
            logger.warning(
                "ocr.pii.blocked",
                extra={
                    "event_name": "ocr.pii.blocked",
                    "component": "pii_guard",
                    "error_code": "sensitive_data_detected",
                    "outcome": "review_required",
                },
            )

        outcome = (
            "review_required"
            if result.get("status") == "review_required"
            else "success"
        )
        log_completion = logger.warning if outcome == "review_required" else logger.info
        log_completion(
            "ocr.tool.completed",
            extra={
                "event_name": "ocr.tool.completed",
                "component": "exam_extractor",
                "duration_ms": _duration_ms(started_at),
                "outcome": outcome,
            },
        )
        return dict(result)

    return server


def create_sse_app(
    image_directory: Path,
    ocr_processor: ExamExtractor,
    allowed_hosts: list[str],
    pii_guard: PiiOutputGuard,
) -> Starlette:
    server = create_server(image_directory, ocr_processor, pii_guard)
    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
    )
    return server.sse_app(
        host="0.0.0.0",
        transport_security=transport_security,
    )


def _duration_ms(started_at: float) -> int:
    return round((monotonic() - started_at) * 1000)
