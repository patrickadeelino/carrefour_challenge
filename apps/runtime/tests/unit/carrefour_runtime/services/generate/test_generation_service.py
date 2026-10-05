import json
from pathlib import Path
from typing import Any

import pytest

from carrefour_runtime.services.generate.service import (
    InvalidAgentSpecification,
    generate_agent_file,
)

RUNTIME_ROOT = Path(__file__).resolve().parents[5]
SPECIFICATION_PATH = RUNTIME_ROOT / "tests" / "fixtures" / "specification.json"


def load_specification() -> dict[str, Any]:
    return json.loads(SPECIFICATION_PATH.read_text(encoding="utf-8"))


def test_generation_service_creates_parent_directory_and_writes_python(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "nested" / "generated" / "agent.py"

    generate_agent_file(load_specification(), output_path)

    source = output_path.read_text(encoding="utf-8")
    assert source.startswith("from typing import Any\n")
    assert "def create_agent(registered_tools" in source


def test_generation_service_rejects_invalid_specification_before_writing(
    tmp_path: Path,
) -> None:
    specification = load_specification()
    specification["agent"]["tools"] = ["medical_order_ocr"]
    output_path = tmp_path / "agent.py"

    with pytest.raises(InvalidAgentSpecification) as error:
        generate_agent_file(specification, output_path)

    assert any("agent.tools" in message for message in error.value.messages)
    assert not output_path.exists()


def test_generation_service_propagates_output_filesystem_failure(
    tmp_path: Path,
) -> None:
    parent_file = tmp_path / "existing-file"
    parent_file.write_text("not a directory", encoding="utf-8")
    output_path = parent_file / "agent.py"

    with pytest.raises(OSError):
        generate_agent_file(load_specification(), output_path)
