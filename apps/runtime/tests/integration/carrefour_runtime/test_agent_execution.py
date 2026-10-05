import asyncio
import importlib.util
import socket
import subprocess
import sys
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import uvicorn
from google.adk.models import BaseLlm, LlmCapabilities
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from PIL import Image

from carrefour_runtime.services.image_storage.temporary_store import TemporaryImageStore
from carrefour_runtime.services.process.adk_executor import AdkOcrExecutor
from carrefour_runtime.services.process.errors import ProcessExecutionError
from carrefour_runtime.services.process.service import ProcessService
from carrefour_runtime.value_objects.exam_result import ExamResult
from support.adk_models import (
    DeterministicOcrModel,
    function_call_response,
    text_response,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SPECIFICATION_PATH = PROJECT_ROOT / "tests" / "fixtures" / "specification.json"


@pytest.fixture(autouse=True)
def disable_google_mtls_for_local_sse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_USE_CLIENT_CERTIFICATE", "false")


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


def generate_agent_or_fail(output_path: Path) -> Path:
    result = run_generate(output_path)
    assert result.returncode == 0, result.stderr or result.stdout
    return output_path


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


def test_runner_executes_each_registered_tool_from_generated_agent(tmp_path):
    output_path = tmp_path / "generated_agent.py"
    generate_agent_or_fail(output_path)

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
            function_call_response(
                "medical_order_ocr", "call-ocr", image_path="pedido.png"
            ),
            function_call_response(
                "exam_catalog_search", "call-search", exam_name="raio-x"
            ),
            function_call_response(
                "appointment_booking", "call-booking", exam_id="exam-123"
            ),
            text_response("Solicitação de agendamento registrada."),
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


@asynccontextmanager
async def serve_fake_ocr(result: object) -> AsyncIterator[tuple[str, list[str]]]:
    server = MCPServer("fake-carrefour-ocr")
    received_image_ids: list[str] = []

    @server.tool()
    async def extract_exams(image_id: str) -> dict[str, object]:
        """Retorna um resultado OCR local e guarda o único argumento recebido."""
        received_image_ids.append(image_id)
        if not isinstance(result, dict):
            raise ValueError("resultado de teste inválido")
        return result

    @server.tool()
    async def unrelated_ocr_tool() -> dict[str, str]:
        """Tool de teste que o runtime não deve expor ao agente."""
        return {"status": "unexpected"}

    app = server.sse_app(
        host="0.0.0.0",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["127.0.0.1:*"],
        ),
    )
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.setblocking(False)
    port = listener.getsockname()[1]
    http_server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    server_task = asyncio.create_task(http_server.serve(sockets=[listener]))

    async def wait_until_started() -> None:
        while not http_server.started:
            if server_task.done():
                server_task.result()
            await asyncio.sleep(0.01)

    try:
        await asyncio.wait_for(wait_until_started(), timeout=5)
        yield f"http://127.0.0.1:{port}/sse", received_image_ids
    finally:
        http_server.should_exit = True
        await server_task
        listener.close()


def synthetic_png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (2, 2), color="white").save(output, format="PNG")
    return output.getvalue()


def make_process_service(
    tmp_path: Path,
    generated_agent_path: Path,
    ocr_mcp_url: str,
    model: DeterministicOcrModel,
) -> tuple[ProcessService, TemporaryImageStore, bytes]:
    images_directory = tmp_path / "images"
    images_directory.mkdir(exist_ok=True)
    original_image = synthetic_png()
    (images_directory / "request.png").write_bytes(original_image)
    image_store = TemporaryImageStore(tmp_path / "temporary")
    executor = AdkOcrExecutor(
        generated_agent_path=generated_agent_path,
        ocr_mcp_url=ocr_mcp_url,
        model_override=model,
    )
    service = ProcessService(
        image_directory=images_directory,
        image_store=image_store,
        executor=executor,
        lock_path=tmp_path / "lock" / "process.lock",
    )
    return service, image_store, original_image


@pytest.mark.parametrize(
    "ocr_result",
    [
        {"exams": ["Hemograma completo", "Glicemia de jejum"]},
        {"exams": []},
        {
            "status": "review_required",
            "exams": ["Hemograma completo"],
            "ambiguous_exams": ["TSH"],
        },
        {
            "status": "review_required",
            "reason": "sensitive_data_detected",
        },
    ],
)
def test_process_runs_generated_agent_over_sse_and_uses_structured_tool_result(
    tmp_path: Path, ocr_result: dict[str, object]
) -> None:
    output_path = tmp_path / "generated" / "agent.py"
    generate_agent_or_fail(output_path)
    deterministic_model = DeterministicOcrModel()

    async def process_request() -> tuple[
        ExamResult, list[str], list[str], TemporaryImageStore, bytes
    ]:
        async with serve_fake_ocr(ocr_result) as (mcp_url, received_image_ids):
            service, image_store, original_image = make_process_service(
                tmp_path, output_path, mcp_url, deterministic_model
            )
            result = await asyncio.wait_for(service.process("request.png"), timeout=15)
            return (
                result,
                received_image_ids,
                deterministic_model.available_tool_names,
                image_store,
                original_image,
            )

    (
        actual,
        received_image_ids,
        available_tool_names,
        image_store,
        original_image,
    ) = asyncio.run(process_request())

    assert actual.to_dict() == ocr_result
    assert len(received_image_ids) == 1
    assert str(UUID(received_image_ids[0])) == received_image_ids[0]
    assert "extract_exams" in available_tool_names
    assert "unrelated_ocr_tool" not in available_tool_names
    assert deterministic_model.request_count == 1
    assert deterministic_model.user_text.strip() == (
        f"image_id: {received_image_ids[0]}"
    )
    assert list(image_store.root.iterdir()) == []
    assert (tmp_path / "images" / "request.png").read_bytes() == original_image


def test_process_removes_image_when_mcp_tool_returns_an_error(tmp_path: Path) -> None:
    output_path = tmp_path / "generated" / "agent.py"
    generate_agent_or_fail(output_path)
    deterministic_model = DeterministicOcrModel()

    async def process_request() -> None:
        async with serve_fake_ocr("simulate an OCR failure") as (mcp_url, _):
            service, image_store, _ = make_process_service(
                tmp_path, output_path, mcp_url, deterministic_model
            )
            with pytest.raises(ProcessExecutionError):
                await asyncio.wait_for(service.process("request.png"), timeout=15)
            assert list(image_store.root.iterdir()) == []

    asyncio.run(process_request())


def test_process_fails_when_agent_does_not_call_ocr_tool(tmp_path: Path) -> None:
    output_path = tmp_path / "generated" / "agent.py"
    generate_agent_or_fail(output_path)
    deterministic_model = DeterministicOcrModel(call_tool=False)

    async def process_request() -> None:
        async with serve_fake_ocr({"exams": []}) as (mcp_url, _):
            service, image_store, _ = make_process_service(
                tmp_path, output_path, mcp_url, deterministic_model
            )
            with pytest.raises(ProcessExecutionError, match="não chamou"):
                await asyncio.wait_for(service.process("request.png"), timeout=15)
            assert list(image_store.root.iterdir()) == []

    asyncio.run(process_request())

    assert deterministic_model.request_count == 1


def test_process_cleans_image_when_mcp_service_is_unavailable(tmp_path: Path) -> None:
    output_path = tmp_path / "generated" / "agent.py"
    generate_agent_or_fail(output_path)
    deterministic_model = DeterministicOcrModel()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()

    async def process_request() -> None:
        service, image_store, _ = make_process_service(
            tmp_path,
            output_path,
            f"http://127.0.0.1:{port}/sse",
            deterministic_model,
        )
        with pytest.raises(ProcessExecutionError, match="OCR indisponível"):
            await asyncio.wait_for(service.process("request.png"), timeout=10)
        assert list(image_store.root.iterdir()) == []

    asyncio.run(process_request())
