from pathlib import Path

from carrefour_runtime.services.process import composition
from carrefour_runtime.value_objects.user_id import UserId


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
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("ZAI_API_KEY", "test-key")
    monkeypatch.setenv(
        "CARREFOUR_SCHEDULE_JWT_SECRET", "test-signing-secret-that-is-at-least-32-bytes"
    )

    image_store = object()
    executor = object()
    schedule_client = object()
    service_arguments = {}
    monkeypatch.setattr(composition, "TemporaryImageStore", lambda: image_store)
    monkeypatch.setattr(
        composition,
        "ScheduleApiClient",
        lambda url, secret: (
            schedule_client
            if (url, secret)
            == (
                "http://schedule-api:8000",
                "test-signing-secret-that-is-at-least-32-bytes",
            )
            else None
        ),
    )
    monkeypatch.setattr(
        composition,
        "AdkWorkflowExecutor",
        lambda path, user_id, client: (
            executor
            if (path, user_id, client)
            == (generated_agent, UserId("user-1"), schedule_client)
            else None
        ),
    )

    class FakeProcessService:
        def __init__(self, **kwargs) -> None:
            service_arguments.update(kwargs)

    monkeypatch.setattr(composition, "ProcessService", FakeProcessService)

    service = composition.create_process_service(UserId("user-1"))

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
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    monkeypatch.setenv(
        "CARREFOUR_SCHEDULE_JWT_SECRET", "test-signing-secret-that-is-at-least-32-bytes"
    )
    monkeypatch.delenv("CARREFOUR_INPUT_IMAGES_DIRECTORY", raising=False)
    monkeypatch.delenv("CARREFOUR_PROCESS_LOCK_PATH", raising=False)

    service_arguments = {}

    class FakeProcessService:
        def __init__(self, **kwargs) -> None:
            service_arguments.update(kwargs)

    monkeypatch.setattr(composition, "TemporaryImageStore", object)
    monkeypatch.setattr(composition, "ScheduleApiClient", lambda *_: object())
    monkeypatch.setattr(composition, "AdkWorkflowExecutor", lambda *_: object())
    monkeypatch.setattr(composition, "ProcessService", FakeProcessService)

    composition.create_process_service(UserId("user-1"))

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
        composition.create_process_service(UserId("user-1"))
    except composition.ProcessConfigurationError as error:
        assert error.error_code == "generated_agent_missing"
        assert "execute generate" in error.public_message
    else:
        raise AssertionError("Esperava configuração inválida do agente gerado")
