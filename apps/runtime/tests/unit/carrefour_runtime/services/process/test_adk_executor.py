from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

import pytest

import carrefour_runtime.services.process.adk_executor as adk_executor_module
from carrefour_runtime.services.process.adk_executor import AdkOcrExecutor
from carrefour_runtime.services.process.errors import ProcessExecutionError
from carrefour_runtime.value_objects.image_id import ImageId


@dataclass
class FakeAdkState:
    result: object = field(default_factory=lambda: {"exams": []})
    discovery_failure: Exception | None = None
    execution_failure: Exception | None = None
    cleanup_failure: Exception | None = None
    toolset_close_calls: int = 0
    runner_close_calls: int = 0


class FakeToolset:
    def __init__(self, state: FakeAdkState) -> None:
        self.state = state

    async def close(self) -> None:
        self.state.toolset_close_calls += 1


class FakeRunner:
    def __init__(self, state: FakeAdkState, agent: object, app_name: str) -> None:
        del agent, app_name
        self.state = state

    async def close(self) -> None:
        self.state.runner_close_calls += 1
        if self.state.cleanup_failure is not None:
            raise self.state.cleanup_failure


def configure_fake_adk(
    monkeypatch: pytest.MonkeyPatch, state: FakeAdkState
) -> AdkOcrExecutor:
    toolset = FakeToolset(state)

    class ConfiguredFakeRunner(FakeRunner):
        def __init__(self, agent: object, app_name: str) -> None:
            super().__init__(state, agent, app_name)

    async def ensure_tool_available(_toolset: FakeToolset) -> None:
        if state.discovery_failure is not None:
            raise state.discovery_failure

    async def run_until_result(
        _runner: FakeRunner, _image_id: ImageId, _app_name: str
    ) -> object:
        if state.execution_failure is not None:
            raise state.execution_failure
        return state.result

    monkeypatch.setattr(adk_executor_module, "McpToolset", FakeToolset)
    monkeypatch.setattr(
        adk_executor_module,
        "build_registered_tools",
        lambda _url: {"medical_order_ocr": toolset},
    )
    monkeypatch.setattr(
        adk_executor_module, "ensure_ocr_tool_available", ensure_tool_available
    )
    monkeypatch.setattr(adk_executor_module, "InMemoryRunner", ConfiguredFakeRunner)
    monkeypatch.setattr(adk_executor_module, "run_until_ocr_result", run_until_result)
    executor = AdkOcrExecutor(Path("unused-agent.py"))
    monkeypatch.setattr(executor, "_create_agent", lambda _tools: object())
    return executor


def test_executor_closes_toolset_if_discovery_fails_before_runner_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeAdkState(
        discovery_failure=ProcessExecutionError(
            "serviço OCR indisponível", error_code="ocr_service_unavailable"
        )
    )
    executor = configure_fake_adk(monkeypatch, state)

    with pytest.raises(ProcessExecutionError) as error:
        asyncio.run(executor.extract_exams(ImageId.new()))

    assert error.value.error_code == "ocr_service_unavailable"
    assert state.toolset_close_calls == 1
    assert state.runner_close_calls == 0


def test_executor_closes_runner_after_successful_ocr_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeAdkState(result={"exams": ["Hemograma completo"]})
    executor = configure_fake_adk(monkeypatch, state)

    result = asyncio.run(executor.extract_exams(ImageId.new()))

    assert result == {"exams": ["Hemograma completo"]}
    assert state.runner_close_calls == 1
    assert state.toolset_close_calls == 0


def test_executor_closes_runner_after_ocr_execution_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeAdkState(execution_failure=RuntimeError("private OCR content"))
    executor = configure_fake_adk(monkeypatch, state)

    with pytest.raises(ProcessExecutionError) as error:
        asyncio.run(executor.extract_exams(ImageId.new()))

    assert error.value.error_code == "agent_execution_failed"
    assert "private OCR content" not in str(error.value)
    assert state.runner_close_calls == 1


def test_executor_reports_sanitized_resource_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = FakeAdkState(cleanup_failure=RuntimeError("private close detail"))
    executor = configure_fake_adk(monkeypatch, state)

    with pytest.raises(ProcessExecutionError) as error:
        asyncio.run(executor.extract_exams(ImageId.new()))

    assert error.value.error_code == "ocr_resource_cleanup_failed"
    assert "private close detail" not in str(error.value)
    assert state.runner_close_calls == 1
