import json
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from carrefour_schedule_api.app import create_app
from carrefour_schedule_api.config import ScheduleApiSettings
from utils.schedule_api import JWT_SECRET


def test_database_startup_failure_logs_sanitized_event(tmp_path, capsys) -> None:
    database_parent = tmp_path / "not-a-directory"
    database_parent.write_text("synthetic blocker")
    settings = ScheduleApiSettings(
        database_path=database_parent / "appointments.sqlite3",
        jwt_secret=JWT_SECRET,
        timezone=ZoneInfo("America/Sao_Paulo"),
    )

    with pytest.raises(RuntimeError), TestClient(create_app(settings)):
        pytest.fail("Application startup should fail for an invalid database path")

    captured = capsys.readouterr()
    event = json.loads(captured.err.splitlines()[-1])
    assert event["event"] == "schedule.database.failed"
    assert event["level"] == "ERROR"
    assert event["error_code"] == "schedule_database_initialization_failed"
    assert "not-a-directory" not in captured.err
