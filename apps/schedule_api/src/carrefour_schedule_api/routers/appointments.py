import logging
from datetime import datetime
from time import perf_counter
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field

from carrefour_schedule_api.authentication import get_authenticated_subject
from carrefour_schedule_api.dependencies import ScheduleAppointmentsDep
from carrefour_schedule_api.domain.models import (
    AppointmentGroup,
    ScheduleResult,
    ScheduleStatus,
)

logger = logging.getLogger(__name__)


class CreateAppointmentsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exam_codes: list[Annotated[str, Field(min_length=1, max_length=40)]] = Field(
        min_length=1,
        max_length=100,
        description="Códigos de exames já resolvidos pelo catálogo/RAG.",
        examples=[["CAT-001", "CAT-002"]],
    )


class AppointmentGroupResponse(BaseModel):
    appointment_id: UUID
    scheduled_at: datetime
    exam_codes: list[str]


class UnscheduledExamResponse(BaseModel):
    exam_code: str
    reason: Literal["no_availability"]


class CreateAppointmentsResponse(BaseModel):
    """Reconciliação de agendamentos novos e existentes."""

    status: ScheduleStatus
    already_scheduled: list[AppointmentGroupResponse]
    newly_scheduled: list[AppointmentGroupResponse]
    not_scheduled: list[UnscheduledExamResponse]


class ErrorDetail(BaseModel):
    code: Literal[
        "invalid_or_missing_bearer_token",
        "invalid_request",
        "schedule_storage_unavailable",
        "schedule_unexpected_failure",
        "http_error",
    ]


class ErrorResponse(BaseModel):
    detail: ErrorDetail


def create_appointments_router() -> APIRouter:
    router = APIRouter()

    @router.post(
        "/appointments",
        summary="Reconcilia e agenda exames",
        description=(
            "Preserva os agendamentos existentes do usuário autenticado e agenda "
            "somente códigos novos. A identidade é obtida do claim `sub` de um "
            "JWT HS256 validado; o corpo não aceita `user_id`. Um horário só pode "
            "ser atribuído a um usuário. Se não houver horário, a resposta HTTP "
            "200 indica `partial` ou `no_availability`."
        ),
        response_model=CreateAppointmentsResponse,
        status_code=status.HTTP_200_OK,
        responses={
            401: {"model": ErrorResponse, "description": "Token ausente ou inválido."},
            422: {"model": ErrorResponse, "description": "Corpo fora do contrato."},
            500: {"model": ErrorResponse, "description": "Falha interna sanitizada."},
            503: {"model": ErrorResponse, "description": "Banco indisponível."},
        },
    )
    def create_appointments(
        request_data: CreateAppointmentsRequest,
        subject: Annotated[str, Depends(get_authenticated_subject)],
        service: ScheduleAppointmentsDep,
        request: Request,
    ) -> CreateAppointmentsResponse:
        started_at = getattr(request.state, "schedule_started_at", perf_counter())
        result = service.schedule(subject, request_data.exam_codes)
        duration_ms = max(0, int((perf_counter() - started_at) * 1000))
        logger.info(
            "schedule.appointments.completed",
            extra={
                "event_name": "schedule.appointments.completed",
                "component": "appointments",
                "duration_ms": duration_ms,
                "outcome": result.status,
            },
        )
        return _to_response(result)

    return router


def _to_response(result: ScheduleResult) -> CreateAppointmentsResponse:
    return CreateAppointmentsResponse(
        status=result.status,
        already_scheduled=[
            _to_group_response(group) for group in result.already_scheduled
        ],
        newly_scheduled=[_to_group_response(group) for group in result.newly_scheduled],
        not_scheduled=[
            UnscheduledExamResponse(exam_code=code, reason="no_availability")
            for code in result.not_scheduled
        ],
    )


def _to_group_response(group: AppointmentGroup) -> AppointmentGroupResponse:
    return AppointmentGroupResponse(
        appointment_id=group.appointment_id,
        scheduled_at=group.scheduled_at,
        exam_codes=list(group.exam_codes),
    )
