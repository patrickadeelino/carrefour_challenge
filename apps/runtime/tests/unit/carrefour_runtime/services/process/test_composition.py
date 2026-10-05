from pathlib import Path

from carrefour_runtime.services.process import composition


def test_create_process_service_composes_configured_runtime_dependencies(
    tmp_path: Path, monkeypatch
) -> None:
    generated_agent = tmp_path / "agent.py"
    generated_agent.write_text("# generated test agent", encoding="utf-8")
    input_images = tmp_path / "input"
    lock_path = tmp_path / "locks" / "process.lock"
    monkeypatch.setenv("CARREFOUR_GENERATED_AGENT_PATH", str(generated_agent))
    monkeypatch.setenv("CARREFOUR_INPUT_IMAGES_DIRECTORY", str(input_images))
    monkeypatch.setenv("CARREFOUR_PROCESS_LOCK_PATH", str(lock_path))
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

    image_store = object()
    executor = object()
    service_arguments = {}
    monkeypatch.setattr(composition, "TemporaryImageStore", lambda: image_store)
    monkeypatch.setattr(
        composition,
        "AdkOcrExecutor",
        lambda path: executor if path == generated_agent else None,
    )

    class FakeProcessService:
        def __init__(self, **kwargs) -> None:
            service_arguments.update(kwargs)

    monkeypatch.setattr(composition, "ProcessService", FakeProcessService)

    service = composition.create_process_service()

    assert isinstance(service, FakeProcessService)
    assert service_arguments == {
        "image_directory": input_images,
        "image_store": image_store,
        "executor": executor,
        "lock_path": lock_path,
    }


def test_create_process_service_uses_runtime_defaults(
    tmp_path: Path, monkeypatch
) -> None:
    generated_agent = tmp_path / "agent.py"
    generated_agent.touch()
    monkeypatch.setenv("CARREFOUR_GENERATED_AGENT_PATH", str(generated_agent))
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.delenv("CARREFOUR_INPUT_IMAGES_DIRECTORY", raising=False)
    monkeypatch.delenv("CARREFOUR_PROCESS_LOCK_PATH", raising=False)

    service_arguments = {}

    class FakeProcessService:
        def __init__(self, **kwargs) -> None:
            service_arguments.update(kwargs)

    monkeypatch.setattr(composition, "TemporaryImageStore", object)
    monkeypatch.setattr(composition, "AdkOcrExecutor", lambda _: object())
    monkeypatch.setattr(composition, "ProcessService", FakeProcessService)

    composition.create_process_service()

    assert service_arguments["image_directory"] == Path(
        "/workspace/tests/fixtures/images"
    )
    assert service_arguments["lock_path"] == Path("/tmp/carrefour-runtime/process.lock")


def test_create_process_service_requires_generated_agent_before_api_key(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv(
        "CARREFOUR_GENERATED_AGENT_PATH", str(tmp_path / "missing-agent.py")
    )
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    try:
        composition.create_process_service()
    except composition.ProcessConfigurationError as error:
        assert error.error_code == "generated_agent_missing"
        assert "execute generate" in error.public_message
    else:
        raise AssertionError("Esperava configuração inválida do agente gerado")
