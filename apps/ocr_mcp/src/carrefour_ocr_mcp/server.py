"""MCP and SSE adapters for the OCR application service."""

from __future__ import annotations

import logging
from pathlib import Path
from time import monotonic

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

from carrefour_ocr_mcp.contracts import ExamExtractor
from carrefour_ocr_mcp.services.exam_processing.errors import ExamProcessingError
from carrefour_ocr_mcp.services.exam_processing.service import ExamProcessingService
from carrefour_ocr_mcp.services.pii_guard import PiiOutputGuard

logger = logging.getLogger(__name__)


def create_server(
    image_directory: Path,
    ocr_processor: ExamExtractor,
    pii_guard: PiiOutputGuard,
) -> MCPServer:
    """Build the MCP adapter around the OCR application service."""
    server = MCPServer("carrefour-ocr")
    processing_service = ExamProcessingService(
        image_directory=image_directory,
        extractor=ocr_processor,
        pii_guard=pii_guard,
    )

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
            result = await processing_service.extract_exams(image_id)
        except ExamProcessingError as error:
            _log_failure(error, started_at)
            raise ToolError(error.public_message) from None

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


def _log_failure(error: ExamProcessingError, started_at: float) -> None:
    log_failure = logger.warning if error.is_rejection else logger.error
    event_name = "ocr.tool.rejected" if error.is_rejection else "ocr.tool.failed"
    log_failure(
        event_name,
        extra={
            "event_name": event_name,
            "component": error.component,
            "duration_ms": _duration_ms(started_at),
            "error_code": error.error_code,
            "error_type": error.error_type,
        },
    )


def _duration_ms(started_at: float) -> int:
    return round((monotonic() - started_at) * 1000)
