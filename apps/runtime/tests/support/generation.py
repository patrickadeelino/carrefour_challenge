"""Shared helpers for tests that generate and load the Python agent artifact."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

from carrefour_runtime.services.generate.service import generate_agent_file

RUNTIME_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPECIFICATION_PATH = RUNTIME_ROOT / "tests" / "fixtures" / "specification.json"


def generate_agent_directly(
    output_path: Path,
    specification_path: Path = DEFAULT_SPECIFICATION_PATH,
) -> Path:
    specification = json.loads(specification_path.read_text(encoding="utf-8"))
    generate_agent_file(specification, output_path)
    return output_path


def generate_agent_or_fail(output_path: Path) -> Path:
    return generate_agent_directly(output_path)


def load_generated_agent(output_path: Path) -> ModuleType:
    module_spec = importlib.util.spec_from_file_location("generated_agent", output_path)
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module
