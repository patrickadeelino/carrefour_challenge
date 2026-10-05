"""Sanitized HTTP error handlers and terminal request log events."""

import logging
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    def handle_http_error(request: Request, error: HTTPException) -> JSONResponse:
        if error.status_code == status.HTTP_401_UNAUTHORIZED:
            code = "invalid_or_missing_bearer_token"
            event = "schedule.appointments.rejected"
        else:
            code = "http_error"
            event = "schedule.request.rejected"
        _log_rejection(request, event, code)
        return JSONResponse(
            status_code=error.status_code,
            headers=error.headers,
            content={"detail": {"code": code}},
        )

    @app.exception_handler(RequestValidationError)
    def handle_validation_error(
        request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        _log_rejection(request, "schedule.appointments.rejected", "invalid_request")
        return JSONResponse(
            status_code=422,
            content={"detail": {"code": "invalid_request"}},
        )

    @app.exception_handler(SQLAlchemyError)
    def handle_database_error(
        request: Request, _error: SQLAlchemyError
    ) -> JSONResponse:
        logger.error(
            "schedule.appointments.failed",
            extra={
                "event_name": "schedule.appointments.failed",
                "component": "persistence",
                "duration_ms": _duration_ms(request),
                "outcome": "failed",
                "error_code": "schedule_storage_unavailable",
                "error_type": "DatabaseError",
            },
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": {"code": "schedule_storage_unavailable"}},
        )


def unexpected_failure_response(request: Request) -> JSONResponse:
    logger.error(
        "schedule.request.failed",
        extra={
            "event_name": "schedule.request.failed",
            "component": "http",
            "duration_ms": _duration_ms(request),
            "outcome": "failed",
            "error_code": "schedule_unexpected_failure",
            "error_type": "UnexpectedError",
        },
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": {"code": "schedule_unexpected_failure"}},
    )


def _log_rejection(request: Request, event: str, code: str) -> None:
    logger.warning(
        event,
        extra={
            "event_name": event,
            "component": "appointments",
            "duration_ms": _duration_ms(request),
            "outcome": "rejected",
            "error_code": code,
            "error_type": "RequestRejected",
        },
    )


def _duration_ms(request: Request) -> int:
    started_at = getattr(request.state, "schedule_started_at", perf_counter())
    return max(0, int((perf_counter() - started_at) * 1000))
