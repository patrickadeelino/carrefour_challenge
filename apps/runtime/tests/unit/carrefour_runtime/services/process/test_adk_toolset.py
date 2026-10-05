from __future__ import annotations

import asyncio

import httpx
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

from carrefour_runtime.services.process.adk_toolset import build_registered_tools
from carrefour_runtime.services.process.schedule_api_client import ScheduleApiClient
from carrefour_runtime.services.process.workflow_state import ProcessWorkflowState
from carrefour_runtime.value_objects.image_id import ImageId
from carrefour_runtime.value_objects.user_id import UserId

JWT_SECRET = "test-signing-secret-that-is-at-least-32-bytes"


def test_registered_tools_are_closed_and_gate_schedule_on_catalog_resolution() -> None:
    state = ProcessWorkflowState(ImageId.new(), UserId("user-1"))
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "already_scheduled": [],
                "newly_scheduled": [],
                "not_scheduled": [],
            },
        )

    client = ScheduleApiClient(
        "http://schedule-api:8000",
        JWT_SECRET,
        transport=httpx.MockTransport(handler),
    )
    tools = build_registered_tools(
        state,
        client,
        ocr_mcp_url="http://ocr.test/sse",
        rag_mcp_url="http://rag.test/sse",
    )

    assert set(tools) == {
        "medical_order_ocr",
        "exam_catalog_search",
        "appointment_booking",
    }
    assert isinstance(tools["medical_order_ocr"], McpToolset)
    assert isinstance(tools["exam_catalog_search"], McpToolset)
    assert asyncio.run(tools["appointment_booking"](["CAT-001"])) == {
        "status": "review_required",
        "reason": "catalog_unresolved",
    }
    assert requests == []
