"""MCP adapter for the local exam search service."""

from __future__ import annotations

import logging
from time import monotonic
from typing import Protocol

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import ValidationError
from starlette.applications import Starlette

from carrefour_rag_mcp.contracts import SearchExamsRequest, SearchExamsResponse

logger = logging.getLogger(__name__)


class ExamSearcher(Protocol):
    """Application boundary used by the MCP tool."""

    def search(self, request: SearchExamsRequest) -> SearchExamsResponse: ...


def create_server(search_service: ExamSearcher) -> MCPServer:
    """Register the catalog lookup tool without exposing a transport."""
    server = MCPServer("carrefour-rag")

    @server.tool()
    async def search_exams(exam_names: list[str]) -> dict[str, object]:
        """Resolve a batch of exam names against the approved catalog."""
        started_at = monotonic()
        try:
            request = SearchExamsRequest(exam_names=tuple(exam_names))
        except ValidationError as error:
            _log_rejection(error, started_at)
            raise ToolError("Invalid search_exams request.") from None

        try:
            result = search_service.search(request).model_dump(mode="json")
        except Exception as error:
            _log_failure(error, started_at)
            raise ToolError("Exam search failed.") from None

        logger.info(
            "rag.search.completed",
            extra={
                "event_name": "rag.search.completed",
                "component": "mcp_tool",
                "duration_ms": _duration_ms(started_at),
                "outcome": "success",
            },
        )
        return result

    return server


def create_sse_app(server: MCPServer, allowed_hosts: list[str]) -> Starlette:
    """Expose an already configured MCP server through protected HTTP+SSE."""
    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
    )
    return server.sse_app(
        host="0.0.0.0",
        transport_security=transport_security,
    )


def _log_rejection(error: ValidationError, started_at: float) -> None:
    logger.warning(
        "rag.search.rejected",
        extra={
            "event_name": "rag.search.rejected",
            "component": "mcp_tool",
            "duration_ms": _duration_ms(started_at),
            "error_code": "invalid_search_request",
            "error_type": type(error).__name__,
            "outcome": "rejected",
        },
    )


def _log_failure(error: Exception, started_at: float) -> None:
    logger.error(
        "rag.search.failed",
        extra={
            "event_name": "rag.search.failed",
            "component": "mcp_tool",
            "duration_ms": _duration_ms(started_at),
            "error_code": "search_execution_failed",
            "error_type": type(error).__name__,
            "outcome": "failed",
        },
    )


def _duration_ms(started_at: float) -> int:
    return round((monotonic() - started_at) * 1000)
