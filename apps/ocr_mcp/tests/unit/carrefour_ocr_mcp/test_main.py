import asyncio
import json
import runpy
from pathlib import Path

import pytest

import carrefour_ocr_mcp.__main__ as server_entrypoint
from carrefour_ocr_mcp.services.pii_guard import PiiConfigurationError
from carrefour_ocr_mcp.vision_client import VisionConfigurationError


def test_allowed_hosts_are_split_trimmed_and_empty_values_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CARREFOUR_OCR_ALLOWED_HOSTS", " localhost , ocr-mcp, ,")

    assert server_entrypoint._allowed_hosts_from_environment() == [
        "localhost",
        "ocr-mcp",
    ]


def test_server_startup_wires_environment_clients_and_sse_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image_directory = tmp_path / "shared-images"
    monkeypatch.setenv("CARREFOUR_IMAGE_STORAGE_PATH", str(image_directory))
    monkeypatch.setenv("CARREFOUR_OCR_ALLOWED_HOSTS", "ocr-mcp,localhost")
    observed: dict[str, object] = {}
    http_client = object()
    vision_client = object()
    extractor = object()
    pii_analyzer = object()
    application = object()

    class FakeAsyncClient:
        async def __aenter__(self) -> object:
            return http_client

        async def __aexit__(self, *args: object) -> None:
            del args

    class FakeConfig:
        def __init__(
            self,
            app,
            host: str,
            port: int,
            log_level: str,
            access_log: bool,
        ) -> None:
            observed["config"] = (app, host, port, log_level, access_log)

    class FakeServer:
        def __init__(self, config: FakeConfig) -> None:
            observed["server_config"] = config

        async def serve(self) -> None:
            observed["served"] = True

    monkeypatch.setattr(server_entrypoint.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(
        server_entrypoint.GoogleCloudVisionClient,
        "from_environment",
        classmethod(lambda cls, client: vision_client),
    )

    def create_extractor(client: object) -> object:
        observed["vision_client"] = client
        return extractor

    def create_app(
        directory: Path, processor: object, hosts: list[str], pii_guard: object
    ) -> object:
        observed["app_arguments"] = (directory, processor, hosts, pii_guard)
        return application

    monkeypatch.setattr(server_entrypoint, "VisionExamExtractor", create_extractor)
    monkeypatch.setattr(
        server_entrypoint,
        "PresidioPiiAnalyzer",
        lambda: pii_analyzer,
    )
    monkeypatch.setattr(server_entrypoint, "create_sse_app", create_app)
    monkeypatch.setattr(server_entrypoint.uvicorn, "Config", FakeConfig)
    monkeypatch.setattr(server_entrypoint.uvicorn, "Server", FakeServer)

    asyncio.run(server_entrypoint._serve())

    assert observed["vision_client"] is vision_client
    app_arguments = observed["app_arguments"]
    assert isinstance(app_arguments, tuple)
    assert app_arguments[:3] == (
        image_directory,
        extractor,
        ["ocr-mcp", "localhost"],
    )
    assert isinstance(app_arguments[3], server_entrypoint.PiiOutputGuard)
    assert app_arguments[3]._analyzer is pii_analyzer
    assert observed["config"] == (application, "0.0.0.0", 8000, "info", False)
    assert observed["served"] is True


def test_server_does_not_start_without_allowed_hosts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CARREFOUR_OCR_ALLOWED_HOSTS", raising=False)
    monkeypatch.setattr(
        server_entrypoint.httpx,
        "AsyncClient",
        lambda: pytest.fail("cliente HTTP não deveria ser criado"),
    )

    with pytest.raises(SystemExit, match="CARREFOUR_OCR_ALLOWED_HOSTS"):
        asyncio.run(server_entrypoint._serve())


def test_main_handles_keyboard_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupt_run(coroutine: object) -> None:
        coroutine.close()
        raise KeyboardInterrupt

    monkeypatch.setattr(server_entrypoint.asyncio, "run", interrupt_run)

    server_entrypoint.main()


def test_module_entrypoint_starts_main_when_executed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[bool] = []

    def run_without_starting_server(coroutine: object) -> None:
        started.append(True)
        coroutine.close()

    monkeypatch.setattr(asyncio, "run", run_without_starting_server)

    runpy.run_path(str(Path(server_entrypoint.__file__)), run_name="__main__")

    assert started == [True]


def test_module_entrypoint_logs_configuration_failure_as_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_startup(coroutine: object) -> None:
        coroutine.close()  # type: ignore[attr-defined]
        raise VisionConfigurationError("synthetic configuration failure")

    monkeypatch.setattr(asyncio, "run", fail_startup)

    with pytest.raises(SystemExit, match="synthetic configuration failure"):
        runpy.run_path(str(Path(server_entrypoint.__file__)), run_name="__main__")

    captured = capsys.readouterr()
    payload = json.loads(captured.err.splitlines()[0])
    assert captured.out == ""
    assert payload["service"] == "ocr-mcp"
    assert payload["event"] == "ocr.configuration.failed"
    assert payload["component"] == "vision_client"
    assert payload["error_code"] == "vision_configuration_invalid"
    assert "synthetic configuration failure" not in captured.err


def test_pii_detector_initialization_failure_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_detail = "private path /tmp/patient-name"
    monkeypatch.setattr(
        server_entrypoint,
        "PresidioPiiAnalyzer",
        lambda: (_ for _ in ()).throw(RuntimeError(secret_detail)),
    )

    with pytest.raises(PiiConfigurationError) as error:
        server_entrypoint._create_pii_guard()

    assert secret_detail not in str(error.value)
    assert error.value.error_code == "pii_configuration_failed"


def test_module_entrypoint_logs_pii_configuration_failure_safely(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret_detail = "private path /tmp/patient-name"

    def fail_startup(coroutine: object) -> None:
        coroutine.close()  # type: ignore[attr-defined]
        raise PiiConfigurationError() from RuntimeError(secret_detail)

    monkeypatch.setattr(asyncio, "run", fail_startup)

    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(Path(server_entrypoint.__file__)), run_name="__main__")

    captured = capsys.readouterr()
    payload = json.loads(captured.err.splitlines()[0])
    assert captured.out == ""
    assert payload["event"] == "ocr.configuration.failed"
    assert payload["component"] == "pii_guard"
    assert payload["error_code"] == "pii_configuration_failed"
    assert secret_detail not in captured.err
    assert secret_detail not in str(error.value)
