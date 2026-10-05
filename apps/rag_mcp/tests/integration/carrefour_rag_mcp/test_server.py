import json

import pytest
from carrefour_observability.logging_config import configure_json_logging
from mcp import Client

from carrefour_rag_mcp.application import create_application
from carrefour_rag_mcp.catalog.errors import CatalogLoadError
from carrefour_rag_mcp.catalog.loader import CatalogLoader
from carrefour_rag_mcp.contracts import SearchExamsRequest, SearchExamsResponse
from carrefour_rag_mcp.server import create_server


class FailingSearchService:
    def __init__(self, error_message: str) -> None:
        self.error_message = error_message

    def search(self, request: SearchExamsRequest) -> SearchExamsResponse:
        raise RuntimeError(self.error_message)


@pytest.mark.anyio
async def test_search_tool_returns_results_and_emits_safe_completion_log(
    capsys: pytest.CaptureFixture[str],
) -> None:
    server = create_application()

    async with Client(server) as client:
        tools = await client.list_tools()
        result = await client.call_tool(
            "search_exams", {"exam_names": ["Hemograma completo"]}
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
            }
        ]
    }
    assert captured.out == ""
    assert [record["event"] for record in records] == [
        "rag.catalog.ready",
        "rag.search.completed",
    ]
    assert records[0]["service"] == "rag-mcp"
    assert records[0]["level"] == "INFO"
    assert records[0]["component"] == "catalog_index"
    assert records[0]["outcome"] == "success"
    assert isinstance(records[0]["duration_ms"], int)
    assert records[1]["level"] == "INFO"
    assert records[1]["component"] == "mcp_tool"
    assert records[1]["outcome"] == "success"
    assert isinstance(records[1]["duration_ms"], int)
    assert "Hemograma completo" not in captured.err
    assert "CAT-001" not in captured.err


@pytest.mark.anyio
async def test_non_exact_search_outcomes_are_valid_tool_successes_without_details(
    capsys: pytest.CaptureFixture[str],
) -> None:
    catalog_json = json.dumps(
        {
            "exams": [
                {
                    "code": "CAT-001",
                    "name": "Hemograma alfa",
                    "aliases": ["PRIVATE_SHARED_PANEL"],
                },
                {
                    "code": "CAT-002",
                    "name": "Hemograma beta",
                    "aliases": ["PRIVATE_SHARED_PANEL"],
                },
            ]
        }
    )
    server = create_application(lambda: CatalogLoader.from_json(catalog_json))

    async with Client(server) as client:
        result = await client.call_tool(
            "search_exams",
            {
                "exam_names": [
                    "PRIVATE_SHARED_PANEL",
                    "Hemograma alfx",
                    "unique-no-match-xyz",
                ]
            },
        )

    captured = capsys.readouterr()
    records = [json.loads(line) for line in captured.err.splitlines()]

    assert [item["status"] for item in result.structured_content["results"]] == [
        "ambiguous",
        "review_required",
        "not_found",
    ]
    assert records[-1]["event"] == "rag.search.completed"
    assert records[-1]["level"] == "INFO"
    assert records[-1]["outcome"] == "success"
    assert isinstance(records[-1]["duration_ms"], int)
    for private_value in (
        "PRIVATE_SHARED_PANEL",
        "Hemograma alfx",
        "unique-no-match-xyz",
        "Hemograma alfa",
        "CAT-001",
        "CAT-002",
    ):
        assert private_value not in captured.err


@pytest.mark.anyio
async def test_invalid_search_request_is_rejected_without_logging_query(
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_query = "PRIVATE_EXAM_MARKER" + ("x" * 150)
    server = create_application()

    async with Client(server) as client:
        result = await client.call_tool("search_exams", {"exam_names": [private_query]})

    captured = capsys.readouterr()
    records = [json.loads(line) for line in captured.err.splitlines()]

    assert result.is_error
    assert records[-1]["event"] == "rag.search.rejected"
    assert records[-1]["level"] == "WARNING"
    assert records[-1]["error_code"] == "invalid_search_request"
    assert records[-1]["error_type"] == "ValidationError"
    assert records[-1]["outcome"] == "rejected"
    assert isinstance(records[-1]["duration_ms"], int)
    assert private_query not in captured.err
    assert captured.out == ""


def test_catalog_startup_failure_emits_safe_log_and_stops_initialization(
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_error = "PRIVATE_CATALOG_FAILURE_MARKER"

    def fail_to_load_catalog():
        raise RuntimeError(private_error)

    with pytest.raises(CatalogLoadError) as error:
        create_application(fail_to_load_catalog)

    captured = capsys.readouterr()
    records = [json.loads(line) for line in captured.err.splitlines()]

    assert error.value.error_code == "catalog_unavailable"
    assert [record["event"] for record in records] == ["rag.catalog.failed"]
    assert records[0]["level"] == "ERROR"
    assert records[0]["component"] == "catalog_loader"
    assert records[0]["error_code"] == "catalog_unavailable"
    assert records[0]["error_type"] == "RuntimeError"
    assert records[0]["outcome"] == "failed"
    assert private_error not in captured.err
    assert captured.out == ""


@pytest.mark.anyio
async def test_search_failure_emits_sanitized_error_event(
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_error = "PRIVATE_SEARCH_FAILURE_MARKER"
    configure_json_logging("carrefour_rag_mcp", "rag-mcp")
    server = create_server(FailingSearchService(private_error))

    async with Client(server) as client:
        result = await client.call_tool(
            "search_exams", {"exam_names": ["Hemograma completo"]}
        )

    captured = capsys.readouterr()
    records = [json.loads(line) for line in captured.err.splitlines()]

    assert result.is_error
    assert len(records) == 1
    assert records[0]["event"] == "rag.search.failed"
    assert records[0]["level"] == "ERROR"
    assert records[0]["component"] == "mcp_tool"
    assert records[0]["error_code"] == "search_execution_failed"
    assert records[0]["error_type"] == "RuntimeError"
    assert records[0]["outcome"] == "failed"
    assert isinstance(records[0]["duration_ms"], int)
    assert private_error not in captured.err
    assert "Hemograma completo" not in captured.err
    assert "Hemograma completo" not in str(result.content)
    assert captured.out == ""
