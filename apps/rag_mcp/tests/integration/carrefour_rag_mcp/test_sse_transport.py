import asyncio
import json
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx2
import pytest
import uvicorn
from mcp import Client
from mcp.client.sse import sse_client
from starlette.applications import Starlette

from carrefour_rag_mcp.application import create_application
from carrefour_rag_mcp.server import create_sse_app


@asynccontextmanager
async def serve_sse_app(app: Starlette) -> AsyncIterator[str]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.setblocking(False)
    port = listener.getsockname()[1]

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="critical",
            access_log=False,
        )
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
async def test_sse_transport_discovers_and_calls_search_exams(
    capsys: pytest.CaptureFixture[str],
) -> None:
    app = create_sse_app(
        create_application(),
        allowed_hosts=["127.0.0.1:*"],
    )

    async with (
        serve_sse_app(app) as server_url,
        Client(sse_client(server_url)) as client,
    ):
        tools = await client.list_tools()
        result = await client.call_tool(
            "search_exams",
            {"exam_names": ["Hemograma completo", "Hemogroma completo"]},
        )

    captured = capsys.readouterr()
    records = [json.loads(line) for line in captured.err.splitlines()]

    assert [tool.name for tool in tools.tools] == ["search_exams"]
    assert result.structured_content == {
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
                "status": "review_required",
                "candidates": [
                    {
                        "canonical_name": "Hemograma completo",
                        "similarity": 94.44444444444444,
                    }
                ],
                "match_method": "fuzzy",
            },
        ]
    }
    assert [record["event"] for record in records] == [
        "rag.catalog.ready",
        "rag.search.completed",
    ]
    assert "Hemograma completo" not in captured.err
    assert "CAT-001" not in captured.err
    assert captured.out == ""


@pytest.mark.anyio
async def test_sse_transport_rejects_untrusted_host() -> None:
    app = create_sse_app(
        create_application(),
        allowed_hosts=["rag-mcp:8000"],
    )

    async with serve_sse_app(app) as server_url:
        with pytest.raises(httpx2.HTTPStatusError):
            async with Client(
                sse_client(server_url, headers={"Host": "attacker.example"})
            ) as client:
                await client.list_tools()


@pytest.mark.anyio
async def test_sse_transport_rejects_invalid_input_without_logging_query(
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_query = "PRIVATE_QUERY_MARKER" + ("x" * 160)
    app = create_sse_app(
        create_application(),
        allowed_hosts=["127.0.0.1:*"],
    )

    async with (
        serve_sse_app(app) as server_url,
        Client(sse_client(server_url)) as client,
    ):
        result = await client.call_tool("search_exams", {"exam_names": [private_query]})

    captured = capsys.readouterr()
    records = [json.loads(line) for line in captured.err.splitlines()]

    assert result.is_error
    assert records[-1]["event"] == "rag.search.rejected"
    assert records[-1]["error_code"] == "invalid_search_request"
    assert private_query not in captured.err
    assert private_query not in str(result.content)
    assert captured.out == ""
