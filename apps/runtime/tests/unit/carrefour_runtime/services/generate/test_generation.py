import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from google.adk.agents import Agent

PROJECT_ROOT = Path(__file__).resolve().parents[5]
SPECIFICATION_PATH = PROJECT_ROOT / "tests" / "fixtures" / "specification.json"


def run_generate(
    output_path: Path, specification_path: Path = SPECIFICATION_PATH
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "carrefour_runtime",
            "generate",
            str(specification_path),
            "--output",
            str(output_path),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def load_generated_agent(output_path: Path):
    module_spec = importlib.util.spec_from_file_location("generated_agent", output_path)
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def medical_order_ocr(image_path: str) -> dict[str, str]:
    """Lê um pedido de exame em uma imagem de teste."""
    return {"image_path": image_path}


def exam_catalog_search(exam_name: str) -> dict[str, str]:
    """Pesquisa um exame no catálogo de teste."""
    return {"exam_name": exam_name}


def appointment_booking(exam_id: str) -> dict[str, str]:
    """Solicita o agendamento de um exame de teste."""
    return {"exam_id": exam_id}


def test_generate_creates_valid_python_agent(tmp_path):
    output_path = tmp_path / "generated" / "agent.py"

    result = run_generate(output_path)

    assert result.returncode == 0, result.stderr or result.stdout
    assert output_path.is_file()
    ast.parse(output_path.read_text(encoding="utf-8"))


def test_generate_includes_the_validated_agent_configuration(tmp_path):
    output_path = tmp_path / "agent.py"

    result = run_generate(output_path)

    assert result.returncode == 0, result.stderr or result.stdout
    source = output_path.read_text(encoding="utf-8")
    assert "AGENT_NAME = 'exam_scheduler_demo'" in source
    assert "MODEL_NAME = 'gemini-3.8-flash'" in source
    assert (
        "TOOL_IDS = ('medical_order_ocr', 'exam_catalog_search', 'appointment_booking')"
    ) in source
    assert "def create_agent(registered_tools" in source


def test_generated_factory_builds_real_adk_agent_from_exact_registered_tools(
    tmp_path,
):
    output_path = tmp_path / "agent.py"
    result = run_generate(output_path)
    assert result.returncode == 0, result.stderr or result.stdout

    generated_agent = load_generated_agent(output_path)
    tool_bindings = {
        "medical_order_ocr": medical_order_ocr,
        "exam_catalog_search": exam_catalog_search,
        "appointment_booking": appointment_booking,
    }

    agent = generated_agent.create_agent(tool_bindings)

    assert isinstance(agent, Agent)
    assert agent.name == "exam_scheduler_demo"
    assert agent.model == "gemini-3.8-flash"
    assert "agendamento de exames" in agent.instruction
    assert agent.tools == list(tool_bindings.values())


def test_generated_factory_rejects_missing_tool_before_creating_agent(
    tmp_path, monkeypatch
):
    output_path = tmp_path / "agent.py"
    result = run_generate(output_path)
    assert result.returncode == 0, result.stderr or result.stdout

    generated_agent = load_generated_agent(output_path)

    def fail_if_agent_is_created(**kwargs):
        raise AssertionError("Agent não deve ser instanciado")

    monkeypatch.setattr(generated_agent, "Agent", fail_if_agent_is_created)
    tool_bindings = {
        "medical_order_ocr": medical_order_ocr,
        "exam_catalog_search": exam_catalog_search,
    }

    with pytest.raises(
        ValueError,
        match="appointment_booking.*ausentes|ausentes.*appointment_booking",
    ):
        generated_agent.create_agent(tool_bindings)


def test_generated_factory_rejects_extra_tool_before_creating_agent(
    tmp_path, monkeypatch
):
    output_path = tmp_path / "agent.py"
    result = run_generate(output_path)
    assert result.returncode == 0, result.stderr or result.stdout

    generated_agent = load_generated_agent(output_path)

    def fail_if_agent_is_created(**kwargs):
        raise AssertionError("Agent não deve ser instanciado")

    monkeypatch.setattr(generated_agent, "Agent", fail_if_agent_is_created)
    tool_bindings = {
        "medical_order_ocr": medical_order_ocr,
        "exam_catalog_search": exam_catalog_search,
        "appointment_booking": appointment_booking,
        "unapproved_tool": medical_order_ocr,
    }

    with pytest.raises(
        ValueError, match="unapproved_tool.*extras|extras.*unapproved_tool"
    ):
        generated_agent.create_agent(tool_bindings)


def test_generate_produces_identical_output_for_same_specification(tmp_path):
    first_output = tmp_path / "first_agent.py"
    second_output = tmp_path / "second_agent.py"

    first_result = run_generate(first_output)
    second_result = run_generate(second_output)

    assert first_result.returncode == 0, first_result.stderr or first_result.stdout
    assert second_result.returncode == 0, second_result.stderr or second_result.stdout
    assert first_output.read_bytes() == second_output.read_bytes()


def test_generate_changes_output_when_agent_name_changes(tmp_path):
    specification = json.loads(SPECIFICATION_PATH.read_text(encoding="utf-8"))
    specification["agent"]["name"] = "exam_scheduler_custom"
    renamed_specification = tmp_path / "renamed_specification.json"
    renamed_specification.write_text(json.dumps(specification), encoding="utf-8")
    default_output = tmp_path / "default_agent.py"
    renamed_output = tmp_path / "renamed_agent.py"

    default_result = run_generate(default_output)
    renamed_result = run_generate(renamed_output, renamed_specification)

    assert default_result.returncode == 0, (
        default_result.stderr or default_result.stdout
    )
    assert renamed_result.returncode == 0, (
        renamed_result.stderr or renamed_result.stdout
    )
    assert default_output.read_bytes() != renamed_output.read_bytes()


def test_generate_is_deterministic_when_tool_order_differs(tmp_path):
    specification = json.loads(SPECIFICATION_PATH.read_text(encoding="utf-8"))
    specification["agent"]["tools"].reverse()
    reordered_specification = tmp_path / "reordered_specification.json"
    reordered_specification.write_text(json.dumps(specification), encoding="utf-8")
    default_output = tmp_path / "default_agent.py"
    reordered_output = tmp_path / "reordered_agent.py"

    default_result = run_generate(default_output)
    reordered_result = run_generate(reordered_output, reordered_specification)

    assert default_result.returncode == 0, (
        default_result.stderr or default_result.stdout
    )
    assert reordered_result.returncode == 0, (
        reordered_result.stderr or reordered_result.stdout
    )
    assert default_output.read_bytes() == reordered_output.read_bytes()


def test_generate_rejects_malformed_json_without_creating_output(tmp_path):
    invalid_specification = tmp_path / "invalid_specification.json"
    invalid_specification.write_text('{"agent":', encoding="utf-8")
    output_path = tmp_path / "agent.py"

    result = run_generate(output_path, invalid_specification)

    assert result.returncode != 0
    assert "JSON inválido" in result.stderr
    assert not output_path.exists()


def test_generate_rejects_invalid_specification_without_creating_output(tmp_path):
    specification = json.loads(SPECIFICATION_PATH.read_text(encoding="utf-8"))
    specification["agent"]["model"]["name"] = "gemini-not-allowed"
    invalid_specification = tmp_path / "invalid_specification.json"
    invalid_specification.write_text(json.dumps(specification), encoding="utf-8")
    output_path = tmp_path / "agent.py"

    result = run_generate(output_path, invalid_specification)

    assert result.returncode != 0
    assert "agent.model.name" in result.stderr
    assert not output_path.exists()
