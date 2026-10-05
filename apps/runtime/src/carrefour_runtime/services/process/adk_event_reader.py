"""Leitura de eventos ADK para capturar a resposta estruturada da tool OCR."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Mapping

from google.adk.events import Event
from google.adk.runners import InMemoryRunner
from google.genai import types

from carrefour_runtime.services.process.errors import ProcessExecutionError
from carrefour_runtime.value_objects.image_id import ImageId

_INVALID_OCR_RESULT = "OCR não retornou um resultado estruturado válido"
PROCESS_TIMEOUT_SECONDS = 90.0


def extract_structured_content(response: object) -> object:
    """Extrai apenas structuredContent de uma resposta de função ADK/MCP."""
    if not isinstance(response, Mapping):
        raise _invalid_ocr_result()
    if response.get("isError") is True or response.get("is_error") is True:
        raise _invalid_ocr_result()
    if "structuredContent" not in response:
        raise _invalid_ocr_result()

    return response["structuredContent"]


async def run_until_ocr_result(
    runner: InMemoryRunner,
    image_id: ImageId,
    app_name: str,
) -> object:
    """Executa o turno e encerra assim que chega a resposta estruturada do OCR."""
    session = await runner.session_service.create_session(
        app_name=app_name,
        user_id="carrefour-runtime",
    )
    events = runner.run_async(
        user_id=session.user_id,
        session_id=session.id,
        new_message=_image_reference_message(image_id),
    )
    has_result, result = await _capture_ocr_result(events)
    if not has_result:
        raise ProcessExecutionError(
            "agente não chamou a ferramenta OCR ou não recebeu um resultado",
            error_code="ocr_tool_result_missing",
            component="adk_event_reader",
        )
    return result


async def _capture_ocr_result(
    events: AsyncGenerator[Event, None],
) -> tuple[bool, object]:
    try:
        async with asyncio.timeout(PROCESS_TIMEOUT_SECONDS):
            async for event in events:
                has_result, result = _result_from_event(event)
                if has_result:
                    return True, result
    finally:
        await events.aclose()

    return False, None


def _image_reference_message(image_id: ImageId) -> types.Content:
    return types.Content(
        role="user",
        parts=[types.Part(text=f"image_id: {image_id}")],
    )


def _result_from_event(event: Event) -> tuple[bool, object]:
    if event.content is None:
        return False, None

    for part in event.content.parts or []:
        function_response = part.function_response
        if function_response is None or function_response.name != "extract_exams":
            continue
        return True, extract_structured_content(function_response.response)

    return False, None


def _invalid_ocr_result() -> ProcessExecutionError:
    return ProcessExecutionError(
        _INVALID_OCR_RESULT,
        error_code="ocr_tool_result_invalid",
        component="adk_event_reader",
    )
