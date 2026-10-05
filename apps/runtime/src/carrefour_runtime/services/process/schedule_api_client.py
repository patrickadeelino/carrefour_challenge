"""Authenticated HTTP client for the local appointment scheduling API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import httpx
import jwt
from pydantic import BaseModel, ConfigDict, ValidationError

from carrefour_runtime.services.process.errors import ProcessExecutionError
from carrefour_runtime.value_objects.user_id import UserId

SCHEDULE_API_TIMEOUT_SECONDS = 10.0
JWT_LIFETIME = timedelta(minutes=5)


class _StrictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _AppointmentGroup(_StrictResponse):
    appointment_id: UUID
    scheduled_at: datetime
    exam_codes: list[str]


class _UnscheduledExam(_StrictResponse):
    exam_code: str
    reason: Literal["no_availability"]


class ScheduleApiResponse(_StrictResponse):
    """Validated business response returned by ``POST /appointments``."""

    status: Literal["completed", "partial", "no_availability"]
    already_scheduled: list[_AppointmentGroup]
    newly_scheduled: list[_AppointmentGroup]
    not_scheduled: list[_UnscheduledExam]

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")


class ScheduleApiClient:
    """POST resolved catalog codes with a short-lived, runtime-signed JWT."""

    def __init__(
        self,
        base_url: str,
        jwt_secret: str,
        *,
        timeout_seconds: float = SCHEDULE_API_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not base_url.startswith("http://") and not base_url.startswith("https://"):
            raise ValueError("URL da Schedule API inválida")
        if len(jwt_secret.encode("utf-8")) < 32:
            raise ValueError("segredo JWT inválido")
        if timeout_seconds <= 0:
            raise ValueError("timeout da Schedule API deve ser positivo")
        self.base_url = base_url.rstrip("/")
        self.jwt_secret = jwt_secret
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def schedule(
        self, user_id: UserId, exam_codes: tuple[str, ...]
    ) -> ScheduleApiResponse:
        """Submit one verified batch and sanitize all transport/API failures."""
        if not exam_codes:
            raise ProcessExecutionError(
                "nenhum exame resolvido para agendamento",
                error_code="schedule_request_empty",
                component="schedule_api_client",
            )

        token = self._create_token(user_id)
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    f"{self.base_url}/appointments",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"exam_codes": list(exam_codes)},
                )
        except httpx.TimeoutException as error:
            raise ProcessExecutionError(
                "tempo máximo de comunicação com o agendamento excedido",
                error_code="schedule_api_timeout",
                component="schedule_api_client",
                error_type=type(error).__name__,
            ) from error
        except httpx.HTTPError as error:
            raise ProcessExecutionError(
                "serviço de agendamento indisponível",
                error_code="schedule_api_unavailable",
                component="schedule_api_client",
                error_type=type(error).__name__,
            ) from error

        if response.status_code >= 500:
            raise ProcessExecutionError(
                "serviço de agendamento indisponível",
                error_code="schedule_api_unavailable",
                component="schedule_api_client",
                error_type="HTTPStatusError",
            )
        if response.status_code in {401, 403}:
            raise ProcessExecutionError(
                "autenticação do serviço de agendamento falhou",
                error_code="schedule_api_authentication_failed",
                component="schedule_api_client",
                error_type="HTTPStatusError",
            )
        if response.status_code != 200:
            raise ProcessExecutionError(
                "serviço de agendamento rejeitou a solicitação",
                error_code="schedule_api_rejected",
                component="schedule_api_client",
                error_type="HTTPStatusError",
            )

        try:
            return ScheduleApiResponse.model_validate_json(response.content)
        except (ValueError, ValidationError):
            raise ProcessExecutionError(
                "serviço de agendamento retornou uma resposta inválida",
                error_code="schedule_api_response_invalid",
                component="schedule_api_client",
                error_type="ResponseValidationError",
            ) from None

    def _create_token(self, user_id: UserId) -> str:
        issued_at = datetime.now(UTC)
        return jwt.encode(
            {
                "sub": user_id.value,
                "iat": issued_at,
                "exp": issued_at + JWT_LIFETIME,
            },
            self.jwt_secret,
            algorithm="HS256",
        )
