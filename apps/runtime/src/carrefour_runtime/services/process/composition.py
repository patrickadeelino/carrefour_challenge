"""Build process dependencies from the runtime container configuration."""

from __future__ import annotations

import os
from pathlib import Path

from carrefour_runtime.services.image_storage.temporary_store import (
    TemporaryImageStore,
)
from carrefour_runtime.services.process.adk_executor import AdkOcrExecutor
from carrefour_runtime.services.process.service import ProcessService

DEFAULT_GENERATED_AGENT_PATH = Path("generated/agent.py")
DEFAULT_INPUT_IMAGES_DIRECTORY = Path("/workspace/tests/fixtures/images")
DEFAULT_PROCESS_LOCK_PATH = Path("/tmp/carrefour-runtime/process.lock")


class ProcessConfigurationError(ValueError):
    """Safe configuration failure required before running the process flow."""

    def __init__(self, message: str, error_code: str) -> None:
        super().__init__(message)
        self.public_message = message
        self.error_code = error_code


def create_process_service() -> ProcessService:
    """Compose storage, ADK executor, and process service from environment."""
    generated_agent_path = Path(
        os.environ.get(
            "CARREFOUR_GENERATED_AGENT_PATH", str(DEFAULT_GENERATED_AGENT_PATH)
        )
    )
    if not generated_agent_path.is_file():
        raise ProcessConfigurationError(
            "Agente gerado ausente; execute generate antes de process.",
            error_code="generated_agent_missing",
        )

    if not os.environ.get("GOOGLE_API_KEY", "").strip():
        raise ProcessConfigurationError(
            "GOOGLE_API_KEY não configurada.",
            error_code="runtime_api_key_missing",
        )

    image_directory = Path(
        os.environ.get(
            "CARREFOUR_INPUT_IMAGES_DIRECTORY",
            str(DEFAULT_INPUT_IMAGES_DIRECTORY),
        )
    )
    lock_path = Path(
        os.environ.get("CARREFOUR_PROCESS_LOCK_PATH", str(DEFAULT_PROCESS_LOCK_PATH))
    )
    return ProcessService(
        image_directory=image_directory,
        image_store=TemporaryImageStore(),
        executor=AdkOcrExecutor(generated_agent_path),
        lock_path=lock_path,
    )
