import json
from typing import Any

import pytest
from carrefour_observability.logging_config import configure_json_logging

import carrefour_rag_mcp.__main__ as entrypoint


def test_allowed_hosts_are_split_trimmed_and_empty_values_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CARREFOUR_RAG_ALLOWED_HOSTS", " rag-mcp:8000, localhost , ,")

    assert entrypoint._allowed_hosts_from_environment() == [
        "rag-mcp:8000",
        "localhost",
    ]


def test_missing_allowed_hosts_fails_with_safe_configuration_log(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("CARREFOUR_RAG_ALLOWED_HOSTS", raising=False)
    configure_json_logging("carrefour_rag_mcp", "rag-mcp")

    with pytest.raises(SystemExit, match="CARREFOUR_RAG_ALLOWED_HOSTS"):
        entrypoint._allowed_hosts_from_environment()

    captured = capsys.readouterr()
    records = [json.loads(line) for line in captured.err.splitlines()]

    assert records == [
        {
            "timestamp": records[0]["timestamp"],
            "level": "ERROR",
            "service": "rag-mcp",
            "event": "rag.configuration.failed",
            "component": "sse_server",
            "error_code": "allowed_hosts_missing",
            "error_type": "SystemExit",
        }
    ]
    assert captured.out == ""


@pytest.mark.anyio
async def test_serve_builds_one_application_and_disables_http_access_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_mcp_server = object()
    expected_app = object()
    application_calls: list[object] = []
    app_calls: list[tuple[object, list[str]]] = []
    config_options: dict[str, Any] = {}
    served = False

    def create_application() -> object:
        application_calls.append(expected_mcp_server)
        return expected_mcp_server

    def create_sse_app(server: object, allowed_hosts: list[str]) -> object:
        app_calls.append((server, allowed_hosts))
        return expected_app

    class FakeConfig:
        def __init__(self, app: object, **options: Any) -> None:
            config_options["app"] = app
            config_options.update(options)

    class FakeServer:
        def __init__(self, config: FakeConfig) -> None:
            config_options["config"] = config

        async def serve(self) -> None:
            nonlocal served
            served = True

    monkeypatch.setenv("CARREFOUR_RAG_ALLOWED_HOSTS", "rag-mcp:8000")
    monkeypatch.setattr(entrypoint, "create_application", create_application)
    monkeypatch.setattr(entrypoint, "create_sse_app", create_sse_app)
    monkeypatch.setattr(entrypoint.uvicorn, "Config", FakeConfig)
    monkeypatch.setattr(entrypoint.uvicorn, "Server", FakeServer)

    await entrypoint._serve()

    assert application_calls == [expected_mcp_server]
    assert app_calls == [(expected_mcp_server, ["rag-mcp:8000"])]
    assert served
    assert config_options == {
        "app": expected_app,
        "host": "0.0.0.0",
        "port": 8000,
        "log_level": "info",
        "access_log": False,
        "config": config_options["config"],
    }
