"""Registro fechado de tools ADK para OCR, catálogo e agendamento."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from google.adk.tools.mcp_tool.mcp_session_manager import SseConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

from carrefour_runtime.services.process.errors import ProcessExecutionError
from carrefour_runtime.services.process.schedule_api_client import ScheduleApiClient
from carrefour_runtime.services.process.workflow_state import ProcessWorkflowState

OCR_MCP_URL = "http://ocr-mcp:8000/sse"
RAG_MCP_URL = "http://rag-mcp:8000/sse"
MCP_CONNECT_TIMEOUT_SECONDS = 5.0
MCP_READ_TIMEOUT_SECONDS = 75.0
logger = logging.getLogger(__name__)


def build_registered_tools(
    workflow_state: ProcessWorkflowState,
    schedule_api_client: ScheduleApiClient,
    ocr_mcp_url: str = OCR_MCP_URL,
    rag_mcp_url: str = RAG_MCP_URL,
) -> dict[str, Any]:
    """Monta o registro fechado de tools exigido pela factory da Fase 1."""
    ocr_toolset = build_ocr_toolset(ocr_mcp_url)
    rag_toolset = build_rag_toolset(rag_mcp_url)

    async def appointment_booking(exam_codes: list[str]) -> dict[str, object]:
        """Agenda todos os códigos previamente resolvidos pelo catálogo."""
        if not workflow_state.can_schedule(exam_codes):
            workflow_state.tool_rejection_code = "unresolved_or_unverified_exam_codes"
            return {"status": "review_required", "reason": "catalog_unresolved"}

        result = await schedule_api_client.schedule(
            workflow_state.user_id,
            tuple(exam_codes),
        )
        workflow_state.record_schedule_result(result)
        logger.info(
            "process.schedule.completed",
            extra={
                "event_name": "process.schedule.completed",
                "component": "schedule_api_client",
                "outcome": result.status,
            },
        )
        return result.to_dict()

    return {
        "medical_order_ocr": ocr_toolset,
        "exam_catalog_search": rag_toolset,
        "appointment_booking": appointment_booking,
    }


def build_ocr_toolset(ocr_mcp_url: str = OCR_MCP_URL) -> McpToolset:
    return _build_mcp_toolset(ocr_mcp_url, "extract_exams")


def build_rag_toolset(rag_mcp_url: str = RAG_MCP_URL) -> McpToolset:
    return _build_mcp_toolset(rag_mcp_url, "search_exams")


def _build_mcp_toolset(mcp_url: str, tool_name: str) -> McpToolset:
    return McpToolset(
        connection_params=SseConnectionParams(
            url=mcp_url,
            timeout=MCP_CONNECT_TIMEOUT_SECONDS,
            sse_read_timeout=MCP_READ_TIMEOUT_SECONDS,
        ),
        tool_filter=[tool_name],
        tool_list_cache_ttl_seconds=60.0,
    )


async def ensure_tool_available(
    toolset: McpToolset,
    expected_tool: str,
    service_name: str,
) -> None:
    """Confirma a conexão SSE e que o servidor expõe a tool esperada."""
    try:
        available_tools = await asyncio.wait_for(
            toolset.get_tools(), timeout=MCP_CONNECT_TIMEOUT_SECONDS
        )
    except Exception as error:
        raise ProcessExecutionError(
            f"serviço {service_name} indisponível",
            error_code=f"{service_name}_service_unavailable",
            component="mcp_sse_client",
            error_type=type(error).__name__,
        ) from error

    if not any(tool.name == expected_tool for tool in available_tools):
        raise ProcessExecutionError(
            f"serviço {service_name} não disponibilizou a ferramenta esperada",
            error_code=f"{service_name}_tool_missing",
            component="mcp_sse_client",
        )
