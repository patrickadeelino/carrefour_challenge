from __future__ import annotations

import asyncio
import re
import socket
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

import httpx
import jwt
import pytest
import uvicorn
from google.adk.models import BaseLlm, LlmCapabilities
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field

from carrefour_runtime.services.process.adk_workflow_executor import (
    AdkWorkflowExecutor,
)
from carrefour_runtime.services.process.errors import ProcessExecutionError
from carrefour_runtime.services.process.schedule_api_client import ScheduleApiClient
from carrefour_runtime.value_objects.image_id import ImageId
from carrefour_runtime.value_objects.process_result import ProcessResult
from carrefour_runtime.value_objects.user_id import UserId
from support.adk_models import function_call_response, text_response
from support.generation import generate_agent_or_fail

JWT_SECRET = "test-signing-secret-that-is-at-least-32-bytes"
APPOINTMENT_ID = "75e39b6b-0ea7-4a4e-bbcc-20b137b1f70d"


class DeterministicWorkflowModel(BaseLlm):
    """Scripts the approved calls without contacting Gemini."""

    model: str = "deterministic-workflow-test-model"
    exam_names: list[str]
    exam_codes: list[str]
    request_count: int = 0
    user_text: str = ""
    available_tools: list[str] = Field(default_factory=list)

    @property
    def capabilities(self) -> LlmCapabilities:
        return LlmCapabilities()

    @classmethod
    def supported_models(cls) -> list[str]:
        return ["deterministic-workflow-test-model"]

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,
    ) -> AsyncGenerator[LlmResponse, None]:
        del stream
        self.request_count += 1
        self.available_tools = sorted(
            declaration.name
            for tool in (llm_request.config.tools or [])
            for declaration in (tool.function_declarations or [])
            if declaration.name is not None
        )
        prompt = " ".join(
            part.text or ""
            for content in llm_request.contents or []
            for part in content.parts or []
        )
        if self.request_count == 1:
            image_id = _image_id_from_prompt(prompt)
            self.user_text = prompt
            yield function_call_response(
                "extract_exams", "ocr-call-1", image_id=image_id
            )
            return
        if self.request_count == 2:
            yield function_call_response(
                "search_exams", "rag-call-1", exam_names=self.exam_names
            )
            return
        if self.request_count == 3:
            yield function_call_response(
                "appointment_booking", "schedule-call-1", exam_codes=self.exam_codes
            )
            return
        yield text_response("Resposta final não deve ser usada pelo runtime.")


def _image_id_from_prompt(prompt: str) -> str:
    match = re.search(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        prompt,
    )
    assert match is not None
    image_id = match.group(0)
    assert str(UUID(image_id)) == image_id
    return image_id


@asynccontextmanager
async def serve_fake_ocr_and_rag(
    ocr_result: dict[str, object],
    rag_result: dict[str, object],
) -> AsyncIterator[tuple[str, str, list[str], list[list[str]]]]:
    received_image_ids: list[str] = []
    received_exam_names: list[list[str]] = []
    ocr_server = _create_ocr_server(ocr_result, received_image_ids)
    rag_server = _create_rag_server(rag_result, received_exam_names)
    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*"],
    )
    servers = [
        _build_sse_server(ocr_server, transport_security),
        _build_sse_server(rag_server, transport_security),
    ]
    listeners = [_open_listener(), _open_listener()]
    ports = [listener.getsockname()[1] for listener in listeners]
    tasks = _start_servers(servers, listeners)

    try:
        await _wait_until_started(servers, tasks)
        yield (
            f"http://127.0.0.1:{ports[0]}/sse",
            f"http://127.0.0.1:{ports[1]}/sse",
            received_image_ids,
            received_exam_names,
        )
    finally:
        await _stop_servers(servers, tasks, listeners)


def _create_ocr_server(
    ocr_result: dict[str, object],
    received_image_ids: list[str],
) -> MCPServer:
    server = MCPServer("integration-fake-ocr")

    @server.tool()
    async def extract_exams(image_id: str) -> dict[str, object]:
        """Return a fixed test result and capture the approved reference."""
        received_image_ids.append(image_id)
        return ocr_result

    return server


def _create_rag_server(
    rag_result: dict[str, object],
    received_exam_names: list[list[str]],
) -> MCPServer:
    server = MCPServer("integration-fake-rag")

    @server.tool()
    async def search_exams(exam_names: list[str]) -> dict[str, object]:
        """Return fixed catalog matches and capture the submitted exam list."""
        received_exam_names.append(exam_names)
        return rag_result

    return server


def _build_sse_server(
    server: MCPServer,
    transport_security: TransportSecuritySettings,
) -> uvicorn.Server:
    app = server.sse_app(host="0.0.0.0", transport_security=transport_security)
    return uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=0,
            log_level="error",
        )
    )


def _start_servers(
    servers: list[uvicorn.Server],
    listeners: list[socket.socket],
) -> list[asyncio.Task[None]]:
    return [
        asyncio.create_task(server.serve(sockets=[listener]))
        for server, listener in zip(servers, listeners, strict=True)
    ]


async def _wait_until_started(
    servers: list[uvicorn.Server],
    tasks: list[asyncio.Task[None]],
) -> None:
    while not all(server.started for server in servers):
        for task in tasks:
            if task.done():
                task.result()
        await asyncio.sleep(0.01)


async def _stop_servers(
    servers: list[uvicorn.Server],
    tasks: list[asyncio.Task[None]],
    listeners: list[socket.socket],
) -> None:
    for server in servers:
        server.should_exit = True
    await asyncio.gather(*tasks)
    for listener in listeners:
        listener.close()


def _open_listener() -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.setblocking(False)
    return listener


def resolved_rag_result() -> dict[str, object]:
    return {
        "results": [
            {
                "input_indices": [0],
                "status": "resolved",
                "code": "CAT-001",
                "canonical_name": "Hemograma completo",
                "match_method": "canonical_exact",
            },
            {
                "input_indices": [1],
                "status": "resolved",
                "code": "CAT-002",
                "canonical_name": "Glicemia de jejum",
                "match_method": "canonical_exact",
            },
        ]
    }


def make_executor(
    agent_path: Path,
    user_id: UserId,
    model: DeterministicWorkflowModel,
    requests: list[httpx.Request],
    ocr_url: str,
    rag_url: str,
    api_status: int = 200,
) -> AdkWorkflowExecutor:
    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        response: dict[str, object] = {
            "status": "completed",
            "already_scheduled": [],
            "newly_scheduled": [
                {
                    "appointment_id": APPOINTMENT_ID,
                    "scheduled_at": "2026-10-05T09:00:00-03:00",
                    "exam_codes": ["CAT-001", "CAT-002"],
                }
            ],
            "not_scheduled": [],
        }
        if api_status != 200:
            return httpx.Response(api_status, json={"detail": "private API error"})
        return httpx.Response(200, json=response)

    schedule_client = ScheduleApiClient(
        "http://schedule-api:8000",
        JWT_SECRET,
        transport=httpx.MockTransport(handler),
    )
    return AdkWorkflowExecutor(
        generated_agent_path=agent_path,
        user_id=user_id,
        schedule_api_client=schedule_client,
        ocr_mcp_url=ocr_url,
        rag_mcp_url=rag_url,
        model_override=model,
    )


def test_agent_runs_ocr_rag_and_authenticated_schedule_in_order(tmp_path: Path) -> None:
    agent_path = tmp_path / "generated" / "agent.py"
    generate_agent_or_fail(agent_path)
    names = ["Hemograma completo", "Glicemia de jejum"]
    model = DeterministicWorkflowModel(
        exam_names=names,
        exam_codes=["CAT-001", "CAT-002"],
    )
    requests: list[httpx.Request] = []

    async def run() -> tuple[ProcessResult, list[str], list[list[str]]]:
        async with serve_fake_ocr_and_rag({"exams": names}, resolved_rag_result()) as (
            ocr_url,
            rag_url,
            image_ids,
            exam_names,
        ):
            executor = make_executor(
                agent_path,
                UserId("user-1"),
                model,
                requests,
                ocr_url,
                rag_url,
            )
            result = await executor.execute(ImageId.new())
            return result, image_ids, exam_names

    result, image_ids, exam_names = asyncio.run(run())

    assert result.exit_code == 0
    assert result.to_dict()["status"] == "completed"
    assert len(image_ids) == 1
    assert str(UUID(image_ids[0])) == image_ids[0]
    assert exam_names == [names]
    assert model.request_count == 3
    assert set(model.available_tools) == {
        "extract_exams",
        "search_exams",
        "appointment_booking",
    }
    assert model.user_text.strip() == f"image_id: {image_ids[0]}"
    assert len(requests) == 1
    assert requests[0].url.path == "/appointments"
    assert requests[0].read() == b'{"exam_codes":["CAT-001","CAT-002"]}'
    claims = jwt.decode(
        requests[0].headers["Authorization"].removeprefix("Bearer "),
        JWT_SECRET,
        algorithms=["HS256"],
    )
    assert claims["sub"] == "user-1"


def test_unresolved_catalog_stops_before_appointment_booking(tmp_path: Path) -> None:
    agent_path = tmp_path / "generated" / "agent.py"
    generate_agent_or_fail(agent_path)
    names = ["Hemograma desconhecido"]
    model = DeterministicWorkflowModel(exam_names=names, exam_codes=["CAT-001"])
    requests: list[httpx.Request] = []
    rag_response = {
        "results": [
            {"input_indices": [0], "status": "not_found", "match_method": "none"}
        ]
    }

    async def run() -> ProcessResult:
        async with serve_fake_ocr_and_rag({"exams": names}, rag_response) as (
            ocr_url,
            rag_url,
            _image_ids,
            _exam_names,
        ):
            executor = make_executor(
                agent_path,
                UserId("user-1"),
                model,
                requests,
                ocr_url,
                rag_url,
            )
            return await executor.execute(ImageId.new())

    result = asyncio.run(run())

    assert result.to_dict() == {
        "status": "review_required",
        "reason": "catalog_unresolved",
    }
    assert result.exit_code == 2
    assert model.request_count == 2
    assert requests == []


def test_ocr_review_stops_before_catalog_and_scheduling(tmp_path: Path) -> None:
    agent_path = tmp_path / "generated" / "agent.py"
    generate_agent_or_fail(agent_path)
    model = DeterministicWorkflowModel(exam_names=[], exam_codes=[])
    requests: list[httpx.Request] = []

    async def run() -> ProcessResult:
        async with serve_fake_ocr_and_rag(
            {"status": "review_required", "reason": "sensitive_data_detected"},
            {"results": []},
        ) as (ocr_url, rag_url, _image_ids, _exam_names):
            executor = make_executor(
                agent_path,
                UserId("user-1"),
                model,
                requests,
                ocr_url,
                rag_url,
            )
            return await executor.execute(ImageId.new())

    result = asyncio.run(run())

    assert result.to_dict() == {
        "status": "review_required",
        "reason": "sensitive_data_detected",
    }
    assert result.exit_code == 2
    assert model.request_count == 1
    assert requests == []


def test_schedule_api_failure_is_sanitized_and_does_not_report_success(
    tmp_path: Path,
) -> None:
    agent_path = tmp_path / "generated" / "agent.py"
    generate_agent_or_fail(agent_path)
    names = ["Hemograma completo", "Glicemia de jejum"]
    model = DeterministicWorkflowModel(
        exam_names=names,
        exam_codes=["CAT-001", "CAT-002"],
    )
    requests: list[httpx.Request] = []

    async def run() -> None:
        async with serve_fake_ocr_and_rag({"exams": names}, resolved_rag_result()) as (
            ocr_url,
            rag_url,
            _image_ids,
            _exam_names,
        ):
            executor = make_executor(
                agent_path,
                UserId("user-1"),
                model,
                requests,
                ocr_url,
                rag_url,
                api_status=503,
            )
            with pytest.raises(ProcessExecutionError) as error:
                await executor.execute(ImageId.new())
            assert error.value.error_code == "schedule_api_unavailable"
            assert "private API error" not in str(error.value)

    asyncio.run(run())
    assert len(requests) == 1
