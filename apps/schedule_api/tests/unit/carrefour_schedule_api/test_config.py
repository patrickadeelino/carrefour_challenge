import json
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from carrefour_schedule_api.app import create_app
from carrefour_schedule_api.config import ScheduleApiSettings

VALID_SECRET = "a-local-test-secret-that-is-at-least-32-bytes"


def test_settings_load_database_and_slot_configuration_from_environment(monkeypatch):
    monkeypatch.setenv("CARREFOUR_SCHEDULE_JWT_SECRET", VALID_SECRET)
    monkeypatch.setenv("CARREFOUR_SCHEDULE_DATABASE_PATH", "/tmp/schedule.sqlite3")
    monkeypatch.setenv("CARREFOUR_SCHEDULE_OPENING_TIME", "08:30")
    monkeypatch.setenv("CARREFOUR_SCHEDULE_HORIZON_DAYS", "7")

    settings = ScheduleApiSettings.from_environment()

    assert settings.database_path == Path("/tmp/schedule.sqlite3")
    assert settings.opening_time == time(8, 30)
    assert settings.horizon_days == 7
    assert settings.timezone == ZoneInfo("America/Sao_Paulo")


def test_settings_reject_missing_or_weak_jwt_secret(monkeypatch):
    monkeypatch.delenv("CARREFOUR_SCHEDULE_JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="CARREFOUR_SCHEDULE_JWT_SECRET"):
        ScheduleApiSettings.from_environment()

    monkeypatch.setenv("CARREFOUR_SCHEDULE_JWT_SECRET", "short")
    with pytest.raises(ValueError, match="32"):
        ScheduleApiSettings.from_environment()


def test_settings_reject_invalid_environment_values(monkeypatch):
    monkeypatch.setenv("CARREFOUR_SCHEDULE_JWT_SECRET", VALID_SECRET)
    monkeypatch.setenv("CARREFOUR_SCHEDULE_OPENING_TIME", "not-a-time")

    with pytest.raises(ValueError, match="CARREFOUR_SCHEDULE_OPENING_TIME"):
        ScheduleApiSettings.from_environment()


@pytest.mark.parametrize(
    ("variable", "value", "message"),
    [
        ("CARREFOUR_SCHEDULE_SLOT_DURATION_MINUTES", "half-hour", "integer"),
        ("CARREFOUR_SCHEDULE_ENABLE_DEMO_TOKEN_ISSUER", "sometimes", "boolean"),
        ("CARREFOUR_SCHEDULE_TIMEZONE", "Mars/Olympus", "TIMEZONE is invalid"),
    ],
)
def test_settings_reject_invalid_environment_configuration(
    monkeypatch, variable: str, value: str, message: str
) -> None:
    monkeypatch.setenv("CARREFOUR_SCHEDULE_JWT_SECRET", VALID_SECRET)
    monkeypatch.setenv(variable, value)

    with pytest.raises(ValueError, match=message):
        ScheduleApiSettings.from_environment()


def test_application_factory_logs_invalid_configuration(monkeypatch, capsys) -> None:
    monkeypatch.setenv("CARREFOUR_SCHEDULE_JWT_SECRET", VALID_SECRET)
    monkeypatch.setenv("CARREFOUR_SCHEDULE_SLOT_DURATION_MINUTES", "0")

    with pytest.raises(RuntimeError, match="configuration is invalid"):
        create_app()

    event = json.loads(capsys.readouterr().err.splitlines()[-1])
    assert event["event"] == "schedule.configuration.failed"
    assert event["error_code"] == "schedule_configuration_invalid"
    assert "slot_duration_minutes" not in str(event)
    assert VALID_SECRET not in str(event)
