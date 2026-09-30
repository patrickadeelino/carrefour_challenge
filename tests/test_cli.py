import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

SPECIFICATION_PATH = Path(__file__).resolve().parents[1] / "specification.json"


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

    project_root = Path(__file__).resolve().parents[1]
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "carrefour_transpiler",
            "validate",
            str(spec_path),
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )


def test_validate_accepts_a_valid_exam_scheduler_spec(tmp_path):
    result = run_validate(tmp_path, load_specification())

    assert result.returncode == 0, result.stderr or result.stdout


def test_validate_rejects_malformed_json(tmp_path):
    result = run_validate(tmp_path, '{"agent":')

    assert result.returncode != 0
    assert "JSON inválido" in result.stderr


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
