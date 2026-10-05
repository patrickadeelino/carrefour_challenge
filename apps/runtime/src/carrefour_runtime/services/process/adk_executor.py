"""Executa o agente gerado com a tool OCR conectada por MCP SSE."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

from google.adk.models import BaseLlm
from google.adk.runners import InMemoryRunner
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

from carrefour_runtime.services.process.adk_event_reader import run_until_ocr_result
from carrefour_runtime.services.process.adk_toolset import (
    OCR_MCP_URL,
    build_registered_tools,
    ensure_ocr_tool_available,
)
from carrefour_runtime.services.process.errors import ProcessExecutionError
from carrefour_runtime.value_objects.image_id import ImageId

RUNTIME_APP_NAME = "carrefour-runtime"
OCR_ONLY_INSTRUCTION = (
    "Você processa pedidos de exames usando somente a ferramenta extract_exams. "
    "Receba o image_id fornecido e chame a ferramenta uma única vez com esse ID. "
    "Não peça nem envie dados pessoais, caminhos, URLs ou conteúdo da imagem. "
    "Não use as ferramentas de catálogo ou agendamento nesta etapa."
)


class AdkOcrExecutor:
    """Carrega a factory gerada e encerra o turno após a resposta estruturada do OCR."""

    def __init__(
        self,
        generated_agent_path: Path,
        ocr_mcp_url: str = OCR_MCP_URL,
        model_override: BaseLlm | None = None,
    ) -> None:
        self.generated_agent_path = generated_agent_path
        self.ocr_mcp_url = ocr_mcp_url
        self.model_override = model_override

    async def extract_exams(self, image_id: ImageId) -> object:
        registered_tools = build_registered_tools(self.ocr_mcp_url)
        toolset = registered_tools["medical_order_ocr"]
        if not isinstance(toolset, McpToolset):
            raise ProcessExecutionError(
                "não foi possível configurar a ferramenta OCR",
                error_code="ocr_tool_configuration_failed",
                component="adk_executor",
            )

        runner: InMemoryRunner | None = None
        result: object = None
        failure: ProcessExecutionError | None = None
        failure_cause: Exception | None = None
        cleanup_failure: Exception | None = None
        try:
            await ensure_ocr_tool_available(toolset)
            agent = self._create_agent(registered_tools)
            runner = InMemoryRunner(agent=agent, app_name=RUNTIME_APP_NAME)
            result = await run_until_ocr_result(runner, image_id, RUNTIME_APP_NAME)
        except ProcessExecutionError as error:
            failure = error
        except TimeoutError as error:
            failure = ProcessExecutionError(
                "tempo máximo do processamento excedido",
                error_code="processing_timeout",
                component="adk_executor",
                error_type=type(error).__name__,
            )
            failure_cause = error
        except Exception as error:
            failure = ProcessExecutionError(
                "falha técnica durante a chamada ao agente ou serviço OCR",
                error_code="agent_execution_failed",
                component="adk_executor",
                error_type=type(error).__name__,
            )
            failure_cause = error
        finally:
            cleanup_failure = await _close_adk_resources(runner, toolset)

        _raise_execution_failures(failure, failure_cause, cleanup_failure)
        return result

    def _create_agent(self, registered_tools: dict[str, Any]) -> Any:
        generated_agent = _load_generated_agent(self.generated_agent_path)
        agent = generated_agent.create_agent(registered_tools)
        agent.instruction = OCR_ONLY_INSTRUCTION
        if self.model_override is not None:
            agent.model = self.model_override
        return agent


async def _close_adk_resources(
    runner: InMemoryRunner | None,
    toolset: McpToolset,
) -> Exception | None:
    try:
        if runner is None:
            await toolset.close()
            return None
        await runner.close()
    except Exception as error:
        return error
    return None


def _raise_execution_failures(
    failure: ProcessExecutionError | None,
    failure_cause: Exception | None,
    cleanup_failure: Exception | None,
) -> None:
    if failure is not None and cleanup_failure is not None:
        combined = ExceptionGroup(
            "Falharam a execução ADK e a finalização de recursos",
            [failure_cause or failure, cleanup_failure],
        )
        raise ProcessExecutionError(
            "falha técnica durante a execução do agente e o encerramento de recursos",
            error_code="agent_execution_and_cleanup_failed",
            component="adk_executor",
            error_type="ExceptionGroup",
        ) from combined
    if failure is not None:
        if failure_cause is not None:
            raise failure from failure_cause
        raise failure
    if cleanup_failure is not None:
        raise ProcessExecutionError(
            "falha técnica ao encerrar a conexão com o serviço OCR",
            error_code="ocr_resource_cleanup_failed",
            component="mcp_sse_client",
            error_type=type(cleanup_failure).__name__,
        ) from cleanup_failure


def _load_generated_agent(path: Path) -> ModuleType:
    if not path.is_file():
        raise ProcessExecutionError(
            "agente gerado ausente; execute generate antes de process",
            error_code="generated_agent_missing",
            component="adk_executor",
        )

    try:
        module_spec = importlib.util.spec_from_file_location(
            "carrefour_generated_agent", path
        )
        if module_spec is None or module_spec.loader is None:
            raise ImportError
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        return module
    except Exception as error:
        raise ProcessExecutionError(
            "não foi possível carregar o agente gerado",
            error_code="generated_agent_load_failed",
            component="adk_executor",
            error_type=type(error).__name__,
        ) from error
