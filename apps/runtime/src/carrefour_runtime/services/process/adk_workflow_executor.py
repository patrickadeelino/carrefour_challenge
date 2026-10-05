"""Run the complete OCR, catalog, and scheduling workflow with the ADK agent."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

from google.adk.agents.context import Context
from google.adk.events import Event
from google.adk.models import BaseLlm
from google.adk.runners import InMemoryRunner
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.genai.types import Content, Part

from carrefour_runtime.services.process.adk_agent_loader import (
    RUNTIME_APP_NAME,
    load_generated_agent,
)
from carrefour_runtime.services.process.adk_toolset import (
    OCR_MCP_URL,
    RAG_MCP_URL,
    build_registered_tools,
    ensure_tool_available,
)
from carrefour_runtime.services.process.errors import ProcessExecutionError
from carrefour_runtime.services.process.schedule_api_client import ScheduleApiClient
from carrefour_runtime.services.process.workflow_state import ProcessWorkflowState
from carrefour_runtime.value_objects.image_id import ImageId
from carrefour_runtime.value_objects.process_result import ProcessResult
from carrefour_runtime.value_objects.user_id import UserId

PROCESS_TIMEOUT_SECONDS = 90.0


class AdkWorkflowExecutor:
    """Execute tools in order and use validated tool data as the final response."""

    def __init__(
        self,
        generated_agent_path: Path,
        user_id: UserId,
        schedule_api_client: ScheduleApiClient,
        *,
        ocr_mcp_url: str = OCR_MCP_URL,
        rag_mcp_url: str = RAG_MCP_URL,
        model_override: BaseLlm | None = None,
    ) -> None:
        self.generated_agent_path = generated_agent_path
        self.user_id = user_id
        self.schedule_api_client = schedule_api_client
        self.ocr_mcp_url = ocr_mcp_url
        self.rag_mcp_url = rag_mcp_url
        self.model_override = model_override

    async def execute(self, image_id: ImageId) -> ProcessResult:
        state = ProcessWorkflowState(image_id, self.user_id)
        registered_tools = build_registered_tools(
            state,
            self.schedule_api_client,
            self.ocr_mcp_url,
            self.rag_mcp_url,
        )
        ocr_toolset = registered_tools["medical_order_ocr"]
        rag_toolset = registered_tools["exam_catalog_search"]
        if not isinstance(ocr_toolset, McpToolset) or not isinstance(
            rag_toolset, McpToolset
        ):
            raise ProcessExecutionError(
                "não foi possível configurar as ferramentas MCP",
                error_code="mcp_tool_configuration_failed",
                component="adk_workflow_executor",
            )

        toolsets = (ocr_toolset, rag_toolset)
        runner: InMemoryRunner | None = None
        result: ProcessResult | None = None
        failure: ProcessExecutionError | None = None
        failure_cause: Exception | None = None
        cleanup_failure: Exception | None = None
        try:
            await ensure_tool_available(ocr_toolset, "extract_exams", "ocr")
            await ensure_tool_available(rag_toolset, "search_exams", "rag")
            agent = self._create_agent(registered_tools, state)
            runner = InMemoryRunner(agent=agent, app_name=RUNTIME_APP_NAME)
            result = await _run_until_terminal_result(runner, image_id, state)
        except ProcessExecutionError as error:
            failure = error
        except TimeoutError as error:
            failure = ProcessExecutionError(
                "tempo máximo do processamento excedido",
                error_code="processing_timeout",
                component="adk_workflow_executor",
                error_type=type(error).__name__,
            )
            failure_cause = error
        except Exception as error:
            failure = ProcessExecutionError(
                "falha técnica durante o fluxo do agente",
                error_code="agent_execution_failed",
                component="adk_workflow_executor",
                error_type=type(error).__name__,
            )
            failure_cause = error
        finally:
            cleanup_failure = await _close_adk_resources(runner, toolsets)

        _raise_execution_failures(failure, failure_cause, cleanup_failure)
        if result is None:
            raise ProcessExecutionError(
                "agente não concluiu o fluxo de atendimento",
                error_code="workflow_result_missing",
                component="adk_workflow_executor",
            )
        return result

    def _create_agent(
        self,
        registered_tools: dict[str, Any],
        state: ProcessWorkflowState,
    ) -> Any:
        generated_agent = load_generated_agent(self.generated_agent_path)
        agent = generated_agent.create_agent(registered_tools)
        agent.before_tool_callback = _before_tool_callback(state)
        agent.after_tool_callback = _after_tool_callback(state)
        if self.model_override is not None:
            agent.model = self.model_override
        return agent


def _before_tool_callback(
    state: ProcessWorkflowState,
) -> Callable[[BaseTool, dict[str, Any], Context], dict[str, Any] | None]:
    def before_tool(
        tool: BaseTool,
        arguments: dict[str, Any],
        context: Context,
    ) -> dict[str, Any] | None:
        del context
        return state.before_tool(tool.name, arguments)

    return before_tool


def _after_tool_callback(
    state: ProcessWorkflowState,
) -> Callable[
    [BaseTool, dict[str, Any], Context, dict[str, Any]], dict[str, Any] | None
]:
    def after_tool(
        tool: BaseTool,
        arguments: dict[str, Any],
        context: Context,
        response: dict[str, Any],
    ) -> dict[str, Any] | None:
        del context
        state.after_tool(tool.name, arguments, response)
        return None

    return after_tool


async def _run_until_terminal_result(
    runner: InMemoryRunner,
    image_id: ImageId,
    state: ProcessWorkflowState,
) -> ProcessResult:
    session = await runner.session_service.create_session(
        app_name=RUNTIME_APP_NAME,
        user_id="carrefour-runtime",
    )
    events = runner.run_async(
        user_id=session.user_id,
        session_id=session.id,
        new_message=_image_reference_message(image_id),
    )
    try:
        async with asyncio.timeout(PROCESS_TIMEOUT_SECONDS):
            async for event in events:
                terminal_result = _result_after_tool_response(event, state)
                if terminal_result is not None:
                    return terminal_result
    finally:
        await events.aclose()

    raise ProcessExecutionError(
        "agente não chamou as ferramentas necessárias para concluir o fluxo",
        error_code="workflow_result_missing",
        component="adk_workflow_executor",
    )


def _result_after_tool_response(
    event: Event,
    state: ProcessWorkflowState,
) -> ProcessResult | None:
    tool_name = _tool_response_name(event)
    if tool_name == "extract_exams":
        return _ocr_terminal_result(state)

    if tool_name == "search_exams":
        return _catalog_terminal_result(state)

    if tool_name == "appointment_booking":
        return _schedule_terminal_result(state)

    if state.tool_rejection_code is not None:
        raise ProcessExecutionError(
            "agente solicitou uma tool fora da sequência aprovada",
            error_code="workflow_tool_rejected",
            component="workflow_guard",
        )
    return None


def _ocr_terminal_result(state: ProcessWorkflowState) -> ProcessResult | None:
    result = state.ocr_result
    if result is None:
        raise _workflow_result_invalid()
    if result.requires_review or not result.exams:
        return state.to_process_result()
    return None


def _catalog_terminal_result(state: ProcessWorkflowState) -> ProcessResult | None:
    if state.catalog_result is None:
        raise _workflow_result_invalid()
    if state.requires_catalog_review:
        return state.to_process_result()
    return None


def _schedule_terminal_result(state: ProcessWorkflowState) -> ProcessResult:
    if state.schedule_result is None:
        raise ProcessExecutionError(
            "agendamento não retornou um resultado válido",
            error_code="schedule_result_invalid",
            component="adk_workflow_executor",
        )
    return state.to_process_result()


def _tool_response_name(event: Event) -> str | None:
    if event.content is None:
        return None
    for part in event.content.parts or []:
        response = part.function_response
        if response is not None:
            return response.name
    return None


def _image_reference_message(image_id: ImageId) -> Content:
    return Content(
        role="user",
        parts=[Part(text=f"image_id: {image_id}")],
    )


async def _close_adk_resources(
    runner: InMemoryRunner | None,
    toolsets: tuple[McpToolset, ...],
) -> Exception | None:
    try:
        if runner is not None:
            await runner.close()
            return None
        for toolset in toolsets:
            await toolset.close()
    except Exception as error:
        return error
    return None


def _raise_execution_failures(
    failure: ProcessExecutionError | None,
    failure_cause: Exception | None,
    cleanup_failure: Exception | None,
) -> None:
    if failure is not None and cleanup_failure is not None:
        raise ProcessExecutionError(
            "falha técnica durante o fluxo do agente e o encerramento de recursos",
            error_code="agent_execution_and_cleanup_failed",
            component="adk_workflow_executor",
            error_type="ExceptionGroup",
        ) from ExceptionGroup(
            "Falharam a execução ADK e a finalização de recursos",
            [failure_cause or failure, cleanup_failure],
        )
    if failure is not None:
        if failure_cause is not None:
            raise failure from failure_cause
        raise failure
    if cleanup_failure is not None:
        raise ProcessExecutionError(
            "falha técnica ao encerrar as conexões MCP",
            error_code="mcp_resource_cleanup_failed",
            component="mcp_sse_client",
            error_type=type(cleanup_failure).__name__,
        ) from cleanup_failure


def _workflow_result_invalid() -> ProcessExecutionError:
    return ProcessExecutionError(
        "tool retornou uma resposta estruturada inválida",
        error_code="workflow_result_invalid",
        component="adk_workflow_executor",
    )
