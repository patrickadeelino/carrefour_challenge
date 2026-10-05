from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest

from carrefour_runtime.services.process.errors import ProcessExecutionError
from carrefour_runtime.services.process.schedule_api_client import ScheduleApiClient
from carrefour_runtime.value_objects.user_id import UserId

JWT_SECRET = "test-signing-secret-that-is-at-least-32-bytes"
APPOINTMENT_ID = "75e39b6b-0ea7-4a4e-bbcc-20b137b1f70d"


def completed_response() -> dict[str, object]:
    return {
        "status": "completed",
        "already_scheduled": [],
        "newly_scheduled": [
            {
                "appointment_id": APPOINTMENT_ID,
                "scheduled_at": "2026-10-05T09:00:00-03:00",
                "exam_codes": ["CAT-001", "CAT-002"],
            }
        ],
        "not_scheduled": [],
    }


def test_schedule_posts_verified_codes_with_runtime_signed_user_token() -> None:
    received: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(200, json=completed_response())

    client = ScheduleApiClient(
        "http://schedule-api:8000", JWT_SECRET, transport=httpx.MockTransport(handler)
    )
    result = asyncio.run(client.schedule(UserId("user-1"), ("CAT-001", "CAT-002")))

    request = received[0]
    claims = jwt.decode(
        request.headers["Authorization"].removeprefix("Bearer "),
        JWT_SECRET,
        algorithms=["HS256"],
    )
    assert request.url.path == "/appointments"
    assert request.read() == b'{"exam_codes":["CAT-001","CAT-002"]}'
    assert claims["sub"] == "user-1"
    assert (
        datetime.now(UTC)
        < datetime.fromtimestamp(claims["exp"], UTC)
        < (datetime.now(UTC) + timedelta(minutes=6))
    )
    assert result.status == "completed"
    assert result.to_dict() == completed_response()
    assert str(result.newly_scheduled[0].appointment_id) == APPOINTMENT_ID


@pytest.mark.parametrize(
    ("status_code", "error_code"),
    [
        (401, "schedule_api_authentication_failed"),
        (422, "schedule_api_rejected"),
        (503, "schedule_api_unavailable"),
    ],
)
def test_schedule_sanitizes_http_errors(status_code: int, error_code: str) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"detail": "private server detail"})

    client = ScheduleApiClient(
        "http://schedule-api:8000", JWT_SECRET, transport=httpx.MockTransport(handler)
    )

    with pytest.raises(ProcessExecutionError) as error:
        asyncio.run(client.schedule(UserId("user-1"), ("CAT-001",)))

    assert error.value.error_code == error_code
    assert "private server detail" not in str(error.value)


def test_schedule_sanitizes_timeout() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private transport detail")

    client = ScheduleApiClient(
        "http://schedule-api:8000", JWT_SECRET, transport=httpx.MockTransport(handler)
    )

    with pytest.raises(ProcessExecutionError) as error:
        asyncio.run(client.schedule(UserId("user-1"), ("CAT-001",)))

    assert error.value.error_code == "schedule_api_timeout"
    assert "private transport detail" not in str(error.value)


def test_schedule_rejects_invalid_success_payload() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "completed", "appointments": []})

    client = ScheduleApiClient(
        "http://schedule-api:8000", JWT_SECRET, transport=httpx.MockTransport(handler)
    )

    with pytest.raises(ProcessExecutionError) as error:
        asyncio.run(client.schedule(UserId("user-1"), ("CAT-001",)))

    assert error.value.error_code == "schedule_api_response_invalid"


def test_schedule_rejects_empty_codes_without_network_call() -> None:
    client = ScheduleApiClient("http://schedule-api:8000", JWT_SECRET)

    with pytest.raises(ProcessExecutionError) as error:
        asyncio.run(client.schedule(UserId("user-1"), ()))

    assert error.value.error_code == "schedule_request_empty"
