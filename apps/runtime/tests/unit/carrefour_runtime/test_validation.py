import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from carrefour_runtime.validation import (
    format_validation_errors,
    parse_specification,
    validate_specification,
)

RUNTIME_ROOT = Path(__file__).resolve().parents[3]
SPECIFICATION_PATH = RUNTIME_ROOT / "tests" / "fixtures" / "specification.json"


def load_specification() -> dict[str, Any]:
    return json.loads(SPECIFICATION_PATH.read_text(encoding="utf-8"))


def test_parse_specification_returns_typed_model() -> None:
    specification = parse_specification(load_specification())

    assert specification.agent.name == "exam_scheduler_demo"
    assert specification.agent.type == "exam_scheduler"


def test_validation_formats_root_level_error_at_json_root() -> None:
    with pytest.raises(ValidationError) as error:
        parse_specification(None)

    assert format_validation_errors(error.value)[0].startswith("$: ")
    assert validate_specification(None) == format_validation_errors(error.value)


def test_validation_formats_nested_error_without_echoing_input() -> None:
    specification = load_specification()
    specification["agent"]["model"]["name"] = "sensitive-unapproved-model"

    errors = validate_specification(specification)

    assert len(errors) == 1
    assert errors[0].startswith("agent.model.name: ")
    assert "sensitive-unapproved-model" not in errors[0]


def test_validation_returns_no_errors_for_valid_specification() -> None:
    assert validate_specification(load_specification()) == []
