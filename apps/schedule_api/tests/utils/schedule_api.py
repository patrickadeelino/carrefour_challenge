"""Reusable HTTP fixtures for schedule API tests."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import jwt
from fastapi.testclient import TestClient

from carrefour_schedule_api.app import create_app
from carrefour_schedule_api.config import ScheduleApiSettings

JWT_SECRET = "test-only-signing-secret-with-at-least-32-bytes"
SANTIAGO_TZ = ZoneInfo("America/Sao_Paulo")
DEFAULT_NOW = datetime(2026, 10, 5, 8, 0, tzinfo=SANTIAGO_TZ)


def access_token(
    subject: str, *, expired: bool = False, secret: str = JWT_SECRET
) -> str:
    expiration = datetime.now(UTC) + timedelta(minutes=1)
    if expired:
        expiration = datetime.now(UTC) - timedelta(minutes=1)
    return jwt.encode({"sub": subject, "exp": expiration}, secret, algorithm="HS256")


@contextmanager
def appointments_client(
    tmp_path: Path,
    *,
    now: datetime | None = None,
    now_provider: Callable[[], datetime] | None = None,
    horizon_days: int = 30,
    jwt_secret: str = JWT_SECRET,
) -> Iterator[TestClient]:
    settings = ScheduleApiSettings(
        database_path=tmp_path / "appointments.sqlite3",
        jwt_secret=jwt_secret,
        horizon_days=horizon_days,
    )
    clock = now_provider or (lambda: now or DEFAULT_NOW)
    with TestClient(create_app(settings, now_provider=clock)) as client:
        yield client


def create_appointments(
    client: TestClient, subject: str, exam_codes: list[str]
) -> dict[str, Any]:
    response = client.post(
        "/appointments",
        headers={"Authorization": f"Bearer {access_token(subject)}"},
        json={"exam_codes": exam_codes},
    )
    assert response.status_code == 200
    return response.json()
