import asyncio
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest
import uvicorn
from mcp import Client
from mcp.client.sse import sse_client
from starlette.applications import Starlette

from carrefour_ocr_mcp.server import create_sse_app
from carrefour_ocr_mcp.services.exam_extractor.vision_exam_extractor import (
    VisionExamExtractor,
)


@asynccontextmanager
async def serve_sse_app(app: Starlette) -> AsyncIterator[str]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.setblocking(False)
    port = listener.getsockname()[1]

    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    server_task = asyncio.create_task(server.serve(sockets=[listener]))

    async def wait_until_started() -> None:
        while not server.started:
            if server_task.done():
                server_task.result()
            await asyncio.sleep(0.01)

    try:
        await asyncio.wait_for(wait_until_started(), timeout=5)
        yield f"http://127.0.0.1:{port}/sse"
    finally:
        server.should_exit = True
        await server_task
        listener.close()


@pytest.mark.anyio
async def test_sse_transport_discovers_and_calls_extract_exams(
    tmp_path: Path,
    numbered_vision_annotation: dict[str, object],
    numbered_request_image: bytes,
    vision_client_factory,
    pii_output_guard,
) -> None:
    image_id = str(uuid4())
    (tmp_path / image_id).write_bytes(numbered_request_image)
    vision_client = vision_client_factory(numbered_vision_annotation)
    extractor = VisionExamExtractor(vision_client)
    app = create_sse_app(
        image_directory=tmp_path,
        ocr_processor=extractor,
        allowed_hosts=["127.0.0.1:*"],
        pii_guard=pii_output_guard,
    )

    async with (
        serve_sse_app(app) as server_url,
        Client(sse_client(server_url)) as client,
    ):
        tools = await client.list_tools()
        result = await client.call_tool("extract_exams", {"image_id": image_id})

    assert [tool.name for tool in tools.tools] == ["extract_exams"]
    assert result.structured_content == {
        "exams": [
            "Hemograma completo",
            "Glicemia de jejum",
            "Hemoglobina glicada (HbA1c)",
            "Colesterol total e frações",
            "TSH (hormônio tireoestimulante)",
        ]
    }
    assert vision_client.received_image == numbered_request_image
