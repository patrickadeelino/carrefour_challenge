import ast
import json

import pytest
from google.adk.agents import Agent

from carrefour_runtime.services.generate.service import InvalidAgentSpecification
from support.generation import (
    DEFAULT_SPECIFICATION_PATH,
    generate_agent_directly,
    load_generated_agent,
)

SPECIFICATION_PATH = DEFAULT_SPECIFICATION_PATH


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

    generate_agent_directly(output_path)

    assert output_path.is_file()
    ast.parse(output_path.read_text(encoding="utf-8"))


def test_generate_includes_the_validated_agent_configuration(tmp_path):
    output_path = tmp_path / "agent.py"

    generate_agent_directly(output_path)

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
    generate_agent_directly(output_path)

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
    generate_agent_directly(output_path)

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
    generate_agent_directly(output_path)

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

    generate_agent_directly(first_output)
    generate_agent_directly(second_output)

    assert first_output.read_bytes() == second_output.read_bytes()


def test_generate_changes_output_when_agent_name_changes(tmp_path):
    specification = json.loads(SPECIFICATION_PATH.read_text(encoding="utf-8"))
    specification["agent"]["name"] = "exam_scheduler_custom"
    renamed_specification = tmp_path / "renamed_specification.json"
    renamed_specification.write_text(json.dumps(specification), encoding="utf-8")
    default_output = tmp_path / "default_agent.py"
    renamed_output = tmp_path / "renamed_agent.py"

    generate_agent_directly(default_output)
    generate_agent_directly(renamed_output, renamed_specification)

    assert default_output.read_bytes() != renamed_output.read_bytes()


def test_generate_is_deterministic_when_tool_order_differs(tmp_path):
    specification = json.loads(SPECIFICATION_PATH.read_text(encoding="utf-8"))
    specification["agent"]["tools"].reverse()
    reordered_specification = tmp_path / "reordered_specification.json"
    reordered_specification.write_text(json.dumps(specification), encoding="utf-8")
    default_output = tmp_path / "default_agent.py"
    reordered_output = tmp_path / "reordered_agent.py"

    generate_agent_directly(default_output)
    generate_agent_directly(reordered_output, reordered_specification)

    assert default_output.read_bytes() == reordered_output.read_bytes()


def test_generate_rejects_invalid_specification_without_creating_output(tmp_path):
    specification = json.loads(SPECIFICATION_PATH.read_text(encoding="utf-8"))
    specification["agent"]["model"]["name"] = "gemini-not-allowed"
    invalid_specification = tmp_path / "invalid_specification.json"
    invalid_specification.write_text(json.dumps(specification), encoding="utf-8")
    output_path = tmp_path / "agent.py"

    with pytest.raises(InvalidAgentSpecification) as error:
        generate_agent_directly(output_path, invalid_specification)

    assert "agent.model.name" in " ".join(error.value.messages)
    assert not output_path.exists()
