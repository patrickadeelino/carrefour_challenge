"""Shared helpers for tests that generate and load the Python agent artifact."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

RUNTIME_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPECIFICATION_PATH = RUNTIME_ROOT / "tests" / "fixtures" / "specification.json"


def run_generate(
    output_path: Path,
    specification_path: Path = DEFAULT_SPECIFICATION_PATH,
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
        cwd=RUNTIME_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def generate_agent_or_fail(output_path: Path) -> Path:
    result = run_generate(output_path)
    assert result.returncode == 0, result.stderr or result.stdout
    return output_path


def load_generated_agent(output_path: Path) -> ModuleType:
    module_spec = importlib.util.spec_from_file_location("generated_agent", output_path)
    assert module_spec is not None
    assert module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module
