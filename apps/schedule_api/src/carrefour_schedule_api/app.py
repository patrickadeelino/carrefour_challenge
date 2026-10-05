"""FastAPI app factory and dependency wiring."""

import logging
from collections.abc import Callable
from datetime import datetime

from carrefour_observability.logging_config import configure_json_logging
from fastapi import FastAPI

from carrefour_schedule_api.config import ScheduleApiSettings
from carrefour_schedule_api.domain.availability import AvailabilityPolicy
from carrefour_schedule_api.errors import register_error_handlers
from carrefour_schedule_api.infrastructure.lifecycle import database_lifespan
from carrefour_schedule_api.middleware import record_request_start
from carrefour_schedule_api.routers.appointments import create_appointments_router

logger = logging.getLogger(__name__)


def create_app(
    settings: ScheduleApiSettings | None = None,
    *,
    now_provider: Callable[[], datetime] | None = None,
) -> FastAPI:
    configure_json_logging("carrefour_schedule_api", "schedule-api")
    try:
        resolved_settings = settings or ScheduleApiSettings.from_environment()
        availability_policy = AvailabilityPolicy(
            timezone=resolved_settings.timezone,
            opening_time=resolved_settings.opening_time,
            closing_time=resolved_settings.closing_time,
            slot_duration_minutes=resolved_settings.slot_duration_minutes,
            horizon_days=resolved_settings.horizon_days,
        )
    except (RuntimeError, ValueError):
        logger.error(
            "schedule.configuration.failed",
            extra={
                "event_name": "schedule.configuration.failed",
                "component": "configuration",
                "outcome": "failed",
                "error_code": "schedule_configuration_invalid",
                "error_type": "ConfigurationError",
            },
        )
        raise RuntimeError("Schedule API configuration is invalid") from None

    app = FastAPI(
        title="Carrefour Schedule API",
        summary="Reconciliação e alocação fictícia de horários para exames.",
        description=(
            "API de demonstração. A identidade vem exclusivamente de um JWT HS256 "
            "validado. A agenda usa slots fictícios de segunda a sexta-feira, no "
            "horário comercial configurado."
        ),
        version="0.1.0",
        lifespan=database_lifespan,
    )
    app.state.settings = resolved_settings
    app.state.availability_policy = availability_policy
    app.state.now_provider = now_provider or (
        lambda: datetime.now(availability_policy.timezone)
    )
    app.middleware("http")(record_request_start)
    register_error_handlers(app)
    app.include_router(create_appointments_router(), tags=["Agendamentos"])
    return app
