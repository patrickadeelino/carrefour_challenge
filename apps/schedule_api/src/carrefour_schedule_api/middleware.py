"""HTTP request timing and sanitized unexpected-error boundary."""

import logging
from time import perf_counter
from uuid import uuid4

from carrefour_observability.logging_config import bind_request_id
from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from carrefour_schedule_api.errors import unexpected_failure_response

logger = logging.getLogger(__name__)


async def record_request_start(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    request.state.schedule_started_at = perf_counter()
    request_id = uuid4().hex
    request.state.request_id = request_id

    with bind_request_id(request_id):
        logger.info(
            "schedule.request.started",
            extra={
                "event_name": "schedule.request.started",
                "component": "http",
                "outcome": "started",
            },
        )
        try:
            response = await call_next(request)
        except Exception:
            response = unexpected_failure_response(request)

        response.headers["X-Request-ID"] = request_id
        return response
