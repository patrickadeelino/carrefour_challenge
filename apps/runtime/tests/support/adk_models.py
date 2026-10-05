"""Modelos e respostas ADK determinísticos para testes locais."""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from google.adk.models import BaseLlm, LlmCapabilities
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import Field


def function_call_response(name: str, call_id: str, **args: Any) -> LlmResponse:
    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        id=call_id,
                        name=name,
                        args=args,
                    )
                )
            ],
        )
    )


def text_response(text: str) -> LlmResponse:
    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part(text=text)],
        )
    )


class DeterministicOcrModel(BaseLlm):
    """Pede uma única chamada OCR para o UUID recebido, sem chamar um LLM."""

    model: str = "deterministic-ocr-test-model"
    call_tool: bool = True
    request_count: int = 0
    available_tool_names: list[str] = Field(default_factory=list)
    user_text: str = ""
    image_id: str | None = None

    @property
    def capabilities(self) -> LlmCapabilities:
        return LlmCapabilities()

    @classmethod
    def supported_models(cls) -> list[str]:
        return ["deterministic-ocr-test-model"]

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        del stream
        self.request_count += 1
        tool_names = {
            declaration.name
            for tool in (llm_request.config.tools or [])
            for declaration in (tool.function_declarations or [])
            if declaration.name is not None
        }
        self.available_tool_names = sorted(tool_names)

        if not self.call_tool or self.request_count > 1:
            yield text_response("resposta final propositalmente não confiável")
            return

        prompt = " ".join(
            part.text or ""
            for content in llm_request.contents or []
            for part in content.parts or []
        )
        self.user_text = prompt
        image_id_match = re.search(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            prompt,
        )
        assert image_id_match is not None
        image_id = image_id_match.group(0)
        self.image_id = image_id
        assert str(UUID(image_id)) == image_id
        yield function_call_response("extract_exams", "ocr-call-1", image_id=image_id)
