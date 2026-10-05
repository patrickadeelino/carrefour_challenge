"""Build process dependencies from the runtime container configuration."""

from __future__ import annotations

import os
from pathlib import Path

from carrefour_runtime.services.image_storage.temporary_store import (
    TemporaryImageStore,
)
from carrefour_runtime.services.process.adk_workflow_executor import (
    AdkWorkflowExecutor,
)
from carrefour_runtime.services.process.schedule_api_client import ScheduleApiClient
from carrefour_runtime.services.process.service import ProcessService
from carrefour_runtime.value_objects.user_id import UserId

DEFAULT_GENERATED_AGENT_PATH = Path("generated/agent.py")
DEFAULT_INPUT_IMAGES_DIRECTORY = Path("/workspace/tests/fixtures/images")
DEFAULT_PROCESS_LOCK_PATH = Path("/tmp/carrefour-runtime/process.lock")
DEFAULT_SCHEDULE_API_URL = "http://schedule-api:8000"


class ProcessConfigurationError(ValueError):
    """Safe configuration failure required before running the process flow."""

    def __init__(self, message: str, error_code: str) -> None:
        super().__init__(message)
        self.public_message = message
        self.error_code = error_code


def create_process_service(user_id: UserId) -> ProcessService:
    """Compose storage, agent, and local scheduling API client from environment."""
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

    if not any(
        os.environ.get(key_name, "").strip()
        for key_name in ("GOOGLE_API_KEY", "ZAI_API_KEY")
    ):
        raise ProcessConfigurationError(
            "GOOGLE_API_KEY ou ZAI_API_KEY não configurada.",
            error_code="runtime_api_key_missing",
        )

    schedule_api_url = os.environ.get(
        "CARREFOUR_SCHEDULE_API_URL", DEFAULT_SCHEDULE_API_URL
    ).strip()
    if not schedule_api_url:
        raise ProcessConfigurationError(
            "CARREFOUR_SCHEDULE_API_URL não configurada.",
            error_code="schedule_api_url_missing",
        )

    schedule_jwt_secret = os.environ.get("CARREFOUR_SCHEDULE_JWT_SECRET", "")
    if len(schedule_jwt_secret.encode("utf-8")) < 32:
        raise ProcessConfigurationError(
            "CARREFOUR_SCHEDULE_JWT_SECRET ausente ou inválida.",
            error_code="schedule_jwt_secret_invalid",
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
    schedule_api_client = ScheduleApiClient(schedule_api_url, schedule_jwt_secret)
    return ProcessService(
        image_directory=image_directory,
        image_store=TemporaryImageStore(),
        executor=AdkWorkflowExecutor(
            generated_agent_path,
            user_id,
            schedule_api_client,
        ),
        lock_path=lock_path,
    )
