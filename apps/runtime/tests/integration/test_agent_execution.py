import asyncio
import importlib.util
import subprocess
import sys
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from google.adk.models import BaseLlm, LlmCapabilities
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPECIFICATION_PATH = PROJECT_ROOT / "tests" / "fixtures" / "specification.json"


def run_generate(output_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "carrefour_runtime",
            "generate",
            str(SPECIFICATION_PATH),
            "--output",
            str(output_path),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def load_generated_agent(output_path: Path) -> Any:
    module_spec = importlib.util.spec_from_file_location("generated_agent", output_path)
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


class DeterministicToolCallingModel(BaseLlm):
    model: str = "deterministic-test-model"
    responses: list[LlmResponse]
    response_index: int = 0

    @property
    def capabilities(self) -> LlmCapabilities:
        return LlmCapabilities()

    @classmethod
    def supported_models(cls) -> list[str]:
        return ["deterministic-test-model"]

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        del llm_request, stream
        response = self.responses[self.response_index]
        self.response_index += 1
        yield response


def _function_call_response(name: str, call_id: str, **args: Any) -> LlmResponse:
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


def _text_response(text: str) -> LlmResponse:
    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part(text=text)],
        )
    )


def test_runner_executes_each_registered_tool_from_generated_agent(tmp_path):
    output_path = tmp_path / "generated_agent.py"
    generation_result = run_generate(output_path)
    assert generation_result.returncode == 0, (
        generation_result.stderr or generation_result.stdout
    )

    generated_agent = load_generated_agent(output_path)
    calls: dict[str, list[dict[str, str]]] = {
        "medical_order_ocr": [],
        "exam_catalog_search": [],
        "appointment_booking": [],
    }

    def medical_order_ocr(image_path: str) -> dict[str, str]:
        """Lê um pedido de exame de teste."""
        calls["medical_order_ocr"].append({"image_path": image_path})
        return {"exam_name": "raio-x"}

    def exam_catalog_search(exam_name: str) -> dict[str, str]:
        """Pesquisa um exame no catálogo de teste."""
        calls["exam_catalog_search"].append({"exam_name": exam_name})
        return {"exam_id": "exam-123"}

    def appointment_booking(exam_id: str) -> dict[str, str]:
        """Solicita o agendamento de um exame de teste."""
        calls["appointment_booking"].append({"exam_id": exam_id})
        return {"booking_id": "booking-456"}

    agent = generated_agent.create_agent(
        {
            "medical_order_ocr": medical_order_ocr,
            "exam_catalog_search": exam_catalog_search,
            "appointment_booking": appointment_booking,
        }
    )
    agent.model = DeterministicToolCallingModel(
        responses=[
            _function_call_response(
                "medical_order_ocr", "call-ocr", image_path="pedido.png"
            ),
            _function_call_response(
                "exam_catalog_search", "call-search", exam_name="raio-x"
            ),
            _function_call_response(
                "appointment_booking", "call-booking", exam_id="exam-123"
            ),
            _text_response("Solicitação de agendamento registrada."),
        ]
    )

    async def run_agent() -> list[Any]:
        runner = InMemoryRunner(agent=agent, app_name="agent_execution_test")
        session = await runner.session_service.create_session(
            app_name="agent_execution_test",
            user_id="integration-test-user",
        )
        events = []
        async for event in runner.run_async(
            user_id=session.user_id,
            session_id=session.id,
            new_message=types.Content(
                role="user",
                parts=[types.Part(text="Agende o exame no pedido anexado.")],
            ),
        ):
            events.append(event)
        return events

    events = asyncio.run(run_agent())

    assert calls == {
        "medical_order_ocr": [{"image_path": "pedido.png"}],
        "exam_catalog_search": [{"exam_name": "raio-x"}],
        "appointment_booking": [{"exam_id": "exam-123"}],
    }
    assert any(
        part.text == "Solicitação de agendamento registrada."
        for event in events
        if event.content is not None
        for part in event.content.parts or []
    )
