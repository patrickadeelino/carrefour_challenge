"""Registro fechado de tools ADK e conexão com o servidor OCR via SSE."""

from __future__ import annotations

import asyncio
from typing import Any

from google.adk.tools.mcp_tool.mcp_session_manager import SseConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

from carrefour_runtime.services.process.errors import ProcessExecutionError

OCR_MCP_URL = "http://ocr-mcp:8000/sse"
MCP_CONNECT_TIMEOUT_SECONDS = 5.0
MCP_READ_TIMEOUT_SECONDS = 75.0


def exam_catalog_search(exam_name: str) -> dict[str, str]:
    """Stub controlado da busca de catálogo, ainda fora do escopo desta etapa."""
    del exam_name
    return {
        "status": "not_implemented",
        "message": "A busca no catálogo ainda não está implementada.",
    }


def appointment_booking(exam_id: str) -> dict[str, str]:
    """Stub controlado de agendamento, ainda fora do escopo desta etapa."""
    del exam_id
    return {
        "status": "not_implemented",
        "message": "O agendamento ainda não está implementado.",
    }


def build_registered_tools(ocr_mcp_url: str = OCR_MCP_URL) -> dict[str, Any]:
    """Monta o registro fechado de tools exigido pela factory da Fase 1."""
    ocr_toolset = McpToolset(
        connection_params=SseConnectionParams(
            url=ocr_mcp_url,
            timeout=MCP_CONNECT_TIMEOUT_SECONDS,
            sse_read_timeout=MCP_READ_TIMEOUT_SECONDS,
        ),
        tool_filter=["extract_exams"],
        tool_list_cache_ttl_seconds=60.0,
    )
    return {
        "medical_order_ocr": ocr_toolset,
        "exam_catalog_search": exam_catalog_search,
        "appointment_booking": appointment_booking,
    }


async def ensure_ocr_tool_available(toolset: McpToolset) -> None:
    """Confirma a conexão SSE e que o servidor expõe a tool esperada."""
    try:
        available_tools = await asyncio.wait_for(
            toolset.get_tools(), timeout=MCP_CONNECT_TIMEOUT_SECONDS
        )
    except Exception as error:
        raise ProcessExecutionError(
            "serviço OCR indisponível",
            error_code="ocr_service_unavailable",
            component="mcp_sse_client",
            error_type=type(error).__name__,
        ) from error

    if not any(tool.name == "extract_exams" for tool in available_tools):
        raise ProcessExecutionError(
            "serviço OCR não disponibilizou a ferramenta extract_exams",
            error_code="ocr_tool_missing",
            component="mcp_sse_client",
        )
