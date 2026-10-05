import json
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from carrefour_runtime import cli
from carrefour_runtime.cli import (
    main,
    print_process_result,
)
from carrefour_runtime.services.generate.service import InvalidAgentSpecification
from carrefour_runtime.services.image_storage.temporary_store import ImageStorageError
from carrefour_runtime.services.process.errors import ProcessExecutionError
from carrefour_runtime.value_objects.exam_result import ExamResult

RUNTIME_ROOT = Path(__file__).resolve().parents[3]
SPECIFICATION_PATH = RUNTIME_ROOT / "tests" / "fixtures" / "specification.json"


def load_specification():
    return json.loads(SPECIFICATION_PATH.read_text(encoding="utf-8"))


def overwrite_json_value(
    specification: dict[str, Any], path: tuple[str, ...], value: Any
):
    parent = specification
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value


def run_validate(tmp_path, contents):
    spec_path = tmp_path / "specification.json"
    if isinstance(contents, str):
        spec_path.write_text(contents, encoding="utf-8")
    else:
        spec_path.write_text(json.dumps(contents), encoding="utf-8")

    return subprocess.run(
        [
            sys.executable,
            "-m",
            "carrefour_runtime",
            "validate",
            str(spec_path),
        ],
        cwd=RUNTIME_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_validate_accepts_a_valid_exam_scheduler_spec(tmp_path):
    result = run_validate(tmp_path, load_specification())

    assert result.returncode == 0, result.stderr or result.stdout


def test_validate_runs_successfully_in_process(capsys):
    exit_code = main(["validate", str(SPECIFICATION_PATH)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"Especificação válida: {SPECIFICATION_PATH}" in captured.out
    assert captured.err == ""


def test_validate_reports_invalid_specification_in_process(tmp_path, capsys):
    specification = load_specification()
    specification["agent"]["type"] = "unknown_agent"
    specification_path = tmp_path / "invalid.json"
    specification_path.write_text(json.dumps(specification), encoding="utf-8")

    exit_code = main(["validate", str(specification_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Erro de validação: agent.type" in captured.err
    assert captured.out == ""


def test_validate_reports_unreadable_specification_in_process(tmp_path, capsys):
    missing_path = tmp_path / "missing.json"

    exit_code = main(["validate", str(missing_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert f"Erro ao ler {missing_path}" in captured.err
    assert captured.out == ""


def test_validate_reports_malformed_json_in_process(tmp_path, capsys):
    malformed_path = tmp_path / "malformed.json"
    malformed_path.write_text('{"agent":', encoding="utf-8")

    exit_code = main(["validate", str(malformed_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "JSON inválido" in captured.err
    assert captured.out == ""


def test_generate_reports_invalid_specification_in_process(tmp_path, capsys):
    specification = load_specification()
    specification["agent"]["model"]["name"] = "unapproved-model"
    specification_path = tmp_path / "invalid.json"
    specification_path.write_text(json.dumps(specification), encoding="utf-8")
    output_path = tmp_path / "generated" / "agent.py"

    exit_code = main(
        ["generate", str(specification_path), "--output", str(output_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Erro de validação: agent.model.name" in captured.err
    assert not output_path.exists()


def test_generate_reports_output_write_error_in_process(tmp_path, monkeypatch, capsys):
    output_path = tmp_path / "agent.py"

    def fail_to_generate(specification, destination):
        del specification, destination
        raise OSError("filesystem detail")

    monkeypatch.setattr(cli, "generate_agent_file", fail_to_generate)

    exit_code = main(
        ["generate", str(SPECIFICATION_PATH), "--output", str(output_path)]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert f"Erro ao gravar {output_path}: filesystem detail" in captured.err
    assert captured.out == ""


def test_generate_reports_generation_validation_error_in_process(
    tmp_path, monkeypatch, capsys
):
    def reject_specification(specification, destination):
        del specification, destination
        raise InvalidAgentSpecification(["agent.tools: configuração incompatível"])

    monkeypatch.setattr(cli, "generate_agent_file", reject_specification)

    exit_code = main(
        ["generate", str(SPECIFICATION_PATH), "--output", str(tmp_path / "agent.py")]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Erro de validação: agent.tools" in captured.err
    assert captured.out == ""


def test_process_requires_generate_to_create_the_agent_first(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    exit_code = main(["process", "--path", "request.png"])

    assert exit_code == 1
    assert "execute generate antes de process" in capsys.readouterr().err


def test_process_requires_gemini_api_key_after_generation(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    generated_agent = tmp_path / "generated" / "agent.py"
    generated_agent.parent.mkdir()
    generated_agent.write_text("", encoding="utf-8")

    exit_code = main(["process", "--path", "request.png"])

    assert exit_code == 1
    assert "GOOGLE_API_KEY não configurada" in capsys.readouterr().err


def test_process_uses_an_injectable_executor_factory(tmp_path, monkeypatch, capsys):
    generated_agent = tmp_path / "generated" / "agent.py"
    generated_agent.parent.mkdir()
    generated_agent.write_text("# generated test agent", encoding="utf-8")
    monkeypatch.setenv("CARREFOUR_GENERATED_AGENT_PATH", str(generated_agent))
    monkeypatch.setenv("GOOGLE_API_KEY", "deterministic-test-key")
    expected = ExamResult.from_mapping({"exams": ["Hemograma completo"]})
    executor = object()
    factory_paths = []
    process_calls = []

    def create_executor(agent_path):
        factory_paths.append(agent_path)
        return executor

    class FakeProcessService:
        def __init__(self, image_directory, image_store, executor, lock_path):
            process_calls.append((image_directory, image_store, executor, lock_path))

        async def process(self, filename):
            process_calls.append(filename)
            return expected

    monkeypatch.setattr(cli, "_create_ocr_executor", create_executor, raising=False)
    monkeypatch.setattr(cli, "ProcessService", FakeProcessService)
    monkeypatch.setattr(cli, "TemporaryImageStore", object)

    exit_code = main(["process", "--path", "request.png"])

    assert factory_paths == [generated_agent]
    assert process_calls[0][2] is executor
    assert process_calls[-1] == "request.png"
    assert exit_code == 0
    assert json.loads(capsys.readouterr().out) == {"exams": ["Hemograma completo"]}


def test_create_ocr_executor_builds_adk_executor(tmp_path):
    from carrefour_runtime.services.process.adk_executor import AdkOcrExecutor

    generated_agent_path = tmp_path / "agent.py"

    executor = cli._create_ocr_executor(generated_agent_path)

    assert isinstance(executor, AdkOcrExecutor)
    assert executor.generated_agent_path == generated_agent_path


@pytest.mark.parametrize(
    ("failure", "expected_message"),
    [
        (ProcessExecutionError("imagem inválida"), "imagem inválida"),
        (ImageStorageError("private filesystem detail"), "armazenamento temporário"),
        (RuntimeError("sensitive patient data"), "falha técnica"),
    ],
)
def test_process_reports_processing_failures_without_leaking_internal_errors(
    tmp_path, monkeypatch, capsys, failure, expected_message
):
    generated_agent = tmp_path / "agent.py"
    generated_agent.write_text("# generated", encoding="utf-8")
    monkeypatch.setenv("CARREFOUR_GENERATED_AGENT_PATH", str(generated_agent))
    monkeypatch.setenv("GOOGLE_API_KEY", "deterministic-test-key")
    monkeypatch.setattr(cli, "_create_ocr_executor", lambda _: object())

    class FailedProcessService:
        def __init__(self, **kwargs):
            del kwargs
            if isinstance(failure, ImageStorageError):
                raise failure

        async def process(self, filename):
            del filename
            raise failure

    monkeypatch.setattr(cli, "ProcessService", FailedProcessService)
    monkeypatch.setattr(cli, "TemporaryImageStore", object)

    exit_code = main(["process", "--path", "request.png"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert expected_message in captured.err
    if isinstance(failure, (ImageStorageError, RuntimeError)) and not isinstance(
        failure, ProcessExecutionError
    ):
        assert str(failure) not in captured.err
    assert captured.out == ""


@pytest.mark.parametrize(
    ("result", "expected_exit_code"),
    [
        ({"exams": ["Hemograma completo"]}, 0),
        ({"exams": []}, 0),
        (
            {
                "status": "review_required",
                "exams": [],
                "ambiguous_exams": ["TSH"],
            },
            2,
        ),
        (
            {
                "status": "review_required",
                "reason": "sensitive_data_detected",
            },
            2,
        ),
    ],
)
def test_process_prints_json_and_uses_distinct_manual_review_exit_code(
    result, expected_exit_code, capsys
):
    exit_code = print_process_result(ExamResult.from_mapping(result))

    captured = capsys.readouterr()
    assert exit_code == expected_exit_code
    assert json.loads(captured.out) == result
    assert captured.err == ""


def test_package_entrypoint_exits_with_cli_result(monkeypatch):
    monkeypatch.setattr(cli, "main", lambda: 7)
    monkeypatch.setattr(sys, "argv", ["carrefour-runtime"])

    with pytest.raises(SystemExit) as error:
        runpy.run_module("carrefour_runtime.__main__", run_name="__main__")

    assert error.value.code == 7


@pytest.mark.parametrize(
    ("path", "value", "expected_error"),
    [
        (("agent", "type"), "arbitrary_agent", "agent.type"),
        (("agent", "model", "provider"), "openai", "agent.model.provider"),
        (
            ("agent", "model", "name"),
            "gemini-not-in-the-allowlist",
            "agent.model.name",
        ),
        (
            ("agent", "tools"),
            [
                "https://attacker.example/mcp",
                "exam_catalog_search",
                "appointment_booking",
            ],
            "agent.tools",
        ),
        (
            ("agent", "tools"),
            ["medical_order_ocr", "medical_order_ocr", "appointment_booking"],
            "agent.tools",
        ),
        (
            ("agent", "tools"),
            ["medical_order_ocr", "exam_catalog_search"],
            "agent.tools",
        ),
        (("agent", "name"), "Exam Scheduler", "agent.name"),
        (("agent", "debug"), True, "agent.debug"),
    ],
)
def test_validate_rejects_invalid_specifications(tmp_path, path, value, expected_error):
    spec = load_specification()
    overwrite_json_value(spec, path, value)

    result = run_validate(tmp_path, spec)

    assert result.returncode != 0
    assert expected_error in result.stderr
