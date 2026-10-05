import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from carrefour_schedule_api.dependencies import get_schedule_appointments
from utils.schedule_api import (
    JWT_SECRET,
    SANTIAGO_TZ,
    access_token,
    appointments_client,
    create_appointments,
)


def test_new_exams_are_created_as_one_authenticated_appointment(tmp_path) -> None:
    with appointments_client(tmp_path) as client:
        body = create_appointments(client, "user-1", ["CAT-001", "CAT-002", "CAT-001"])

    assert body["status"] == "completed"
    assert body["already_scheduled"] == []
    assert body["not_scheduled"] == []
    assert len(body["newly_scheduled"]) == 1
    appointment = body["newly_scheduled"][0]
    assert UUID(appointment["appointment_id"])
    assert appointment["exam_codes"] == ["CAT-001", "CAT-002"]
    scheduled_at = datetime.fromisoformat(appointment["scheduled_at"])
    assert scheduled_at.utcoffset() is not None
    assert appointment["scheduled_at"] == "2026-10-05T09:00:00-03:00"


def test_existing_exams_keep_their_slot_and_only_new_exams_are_scheduled(
    tmp_path,
) -> None:
    with appointments_client(tmp_path) as client:
        create_appointments(client, "user-1", ["CAT-001", "CAT-002"])
        body = create_appointments(client, "user-1", ["CAT-002", "CAT-001", "CAT-003"])

    assert body["status"] == "completed"
    assert body["already_scheduled"][0]["scheduled_at"] == ("2026-10-05T09:00:00-03:00")
    assert body["already_scheduled"][0]["exam_codes"] == ["CAT-002", "CAT-001"]
    assert len(body["newly_scheduled"]) == 1
    assert body["newly_scheduled"][0]["scheduled_at"] == ("2026-10-05T09:30:00-03:00")
    assert body["newly_scheduled"][0]["exam_codes"] == ["CAT-003"]


def test_different_users_cannot_receive_the_same_slot(tmp_path) -> None:
    with appointments_client(tmp_path) as client:
        first_user = create_appointments(client, "user-1", ["CAT-001"])
        second_user = create_appointments(client, "user-2", ["CAT-002"])

    assert first_user["newly_scheduled"][0]["scheduled_at"] == (
        "2026-10-05T09:00:00-03:00"
    )
    assert second_user["newly_scheduled"][0]["scheduled_at"] == (
        "2026-10-05T09:30:00-03:00"
    )


def test_missing_bearer_token_is_rejected(tmp_path) -> None:
    with appointments_client(tmp_path) as client:
        response = client.post("/appointments", json={"exam_codes": ["CAT-001"]})

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "invalid_or_missing_bearer_token"}}


def test_invalid_bearer_token_is_rejected(tmp_path) -> None:
    with appointments_client(tmp_path) as client:
        response = client.post(
            "/appointments",
            headers={"Authorization": "Bearer malformed-token"},
            json={"exam_codes": ["CAT-001"]},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "invalid_or_missing_bearer_token"}}


def test_expired_bearer_token_is_rejected(tmp_path) -> None:
    with appointments_client(tmp_path) as client:
        response = client.post(
            "/appointments",
            headers={"Authorization": f"Bearer {access_token('user-1', expired=True)}"},
            json={"exam_codes": ["CAT-001"]},
        )

    assert response.status_code == 401


def test_blank_subject_is_rejected(tmp_path) -> None:
    with appointments_client(tmp_path) as client:
        response = client.post(
            "/appointments",
            headers={"Authorization": f"Bearer {access_token(' ')}"},
            json={"exam_codes": ["CAT-001"]},
        )

    assert response.status_code == 401


def test_request_rejects_fields_outside_the_contract(tmp_path) -> None:
    with appointments_client(tmp_path) as client:
        response = client.post(
            "/appointments",
            headers={"Authorization": f"Bearer {access_token('user-1')}"},
            json={"exam_codes": ["CAT-001"], "user_id": "spoofed-user"},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "invalid_request"}}


def test_request_rejects_empty_exam_list(tmp_path) -> None:
    with appointments_client(tmp_path) as client:
        response = client.post(
            "/appointments",
            headers={"Authorization": f"Bearer {access_token('user-1')}"},
            json={"exam_codes": []},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "invalid_request"}}


def test_no_available_slot_returns_a_business_result(tmp_path) -> None:
    saturday = datetime(2026, 10, 10, 8, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
    with appointments_client(tmp_path, now=saturday, horizon_days=0) as client:
        response = client.post(
            "/appointments",
            headers={"Authorization": f"Bearer {access_token('user-1')}"},
            json={"exam_codes": ["CAT-001"]},
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "no_availability",
        "already_scheduled": [],
        "newly_scheduled": [],
        "not_scheduled": [{"exam_code": "CAT-001", "reason": "no_availability"}],
    }


def test_existing_exams_and_unavailable_new_exams_return_partial(tmp_path) -> None:
    current_time = [datetime(2026, 10, 5, 8, 0, tzinfo=SANTIAGO_TZ)]
    with appointments_client(
        tmp_path,
        now_provider=lambda: current_time[0],
        horizon_days=0,
    ) as client:
        create_appointments(client, "user-1", ["CAT-001"])
        current_time[0] = datetime(2026, 10, 5, 17, 0, tzinfo=SANTIAGO_TZ)
        body = create_appointments(client, "user-1", ["CAT-001", "CAT-002"])

    assert body["status"] == "partial"
    assert body["already_scheduled"][0]["exam_codes"] == ["CAT-001"]
    assert body["not_scheduled"] == [
        {"exam_code": "CAT-002", "reason": "no_availability"}
    ]


def test_appointments_persist_across_application_lifecycles(tmp_path) -> None:
    with appointments_client(tmp_path) as first_client:
        created = create_appointments(first_client, "user-1", ["CAT-001"])
    with appointments_client(tmp_path) as restarted_client:
        repeated = create_appointments(restarted_client, "user-1", ["CAT-001"])

    assert repeated["newly_scheduled"] == []
    assert repeated["already_scheduled"] == created["newly_scheduled"]


def test_concurrent_users_are_assigned_distinct_global_slots(tmp_path) -> None:
    with (
        appointments_client(tmp_path) as client,
        ThreadPoolExecutor(max_workers=2) as executor,
    ):
        results = list(
            executor.map(
                lambda user: create_appointments(client, user, ["CAT-001"]),
                ["user-1", "user-2"],
            )
        )

    scheduled_times = {
        result["newly_scheduled"][0]["scheduled_at"] for result in results
    }
    assert scheduled_times == {
        "2026-10-05T09:00:00-03:00",
        "2026-10-05T09:30:00-03:00",
    }


def test_concurrent_retries_for_the_same_user_are_idempotent(tmp_path) -> None:
    with (
        appointments_client(tmp_path) as client,
        ThreadPoolExecutor(max_workers=2) as executor,
    ):
        results = list(
            executor.map(
                lambda _: create_appointments(client, "user-1", ["CAT-001"]),
                range(2),
            )
        )

    assert sum(len(result["newly_scheduled"]) for result in results) == 1
    assert sum(len(result["already_scheduled"]) for result in results) == 1
    appointment_ids = {
        result[key][0]["appointment_id"]
        for result in results
        for key in ("newly_scheduled", "already_scheduled")
        if result[key]
    }
    assert len(appointment_ids) == 1


def test_database_failure_rolls_back_and_returns_sanitized_error(
    tmp_path, capsys
) -> None:
    with appointments_client(tmp_path) as client:
        database_path = client.app.state.settings.database_path
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                """
                CREATE TRIGGER fail_synthetic_exam
                BEFORE INSERT ON appointment_exams
                WHEN NEW.exam_code = 'SYNTHETIC-FAILURE-MARKER'
                BEGIN SELECT RAISE(ABORT, 'RAW-DATABASE-MARKER'); END
                """
            )
        response = client.post(
            "/appointments",
            headers={"Authorization": f"Bearer {access_token('SECRET-SUBJECT')}"},
            json={"exam_codes": ["SYNTHETIC-FAILURE-MARKER"]},
        )
        with sqlite3.connect(database_path) as connection:
            connection.execute("DROP TRIGGER fail_synthetic_exam")
        retry = create_appointments(client, "user-2", ["CAT-001"])

    captured = capsys.readouterr()
    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "schedule_storage_unavailable"}}
    assert retry["newly_scheduled"][0]["scheduled_at"] == ("2026-10-05T09:00:00-03:00")
    assert "SECRET-SUBJECT" not in captured.err
    assert "SYNTHETIC-FAILURE-MARKER" not in captured.err
    assert "RAW-DATABASE-MARKER" not in captured.err


def test_logs_are_structured_and_do_not_contain_request_data(tmp_path, capsys) -> None:
    with appointments_client(tmp_path) as client:
        completed_response = client.post(
            "/appointments",
            headers={
                "Authorization": f"Bearer {access_token('SECRET-SUBJECT')}",
                "X-Request-ID": "UNTRUSTED-REQUEST-ID-MARKER",
            },
            json={"exam_codes": ["SECRET-EXAM-CODE"]},
        )
        rejected_response = client.post(
            "/appointments", json={"exam_codes": ["SECRET-EXAM-CODE"]}
        )

    captured = capsys.readouterr()
    events = [json.loads(line) for line in captured.err.splitlines()]
    completed_request_id = completed_response.headers["X-Request-ID"]
    rejected_request_id = rejected_response.headers["X-Request-ID"]
    assert captured.out == ""
    assert completed_response.status_code == 200
    assert rejected_response.status_code == 401
    assert completed_request_id != rejected_request_id
    assert len(completed_request_id) == 32
    assert completed_request_id != "UNTRUSTED-REQUEST-ID-MARKER"
    assert any(event["event"] == "schedule.appointments.completed" for event in events)
    assert any(event["event"] == "schedule.appointments.rejected" for event in events)
    assert all(event["service"] == "schedule-api" for event in events)
    assert all("timestamp" in event and "component" in event for event in events)
    assert all(
        "duration_ms" in event for event in events if "appointments" in event["event"]
    )
    completed = next(
        event for event in events if event["event"] == "schedule.appointments.completed"
    )
    rejected = next(
        event for event in events if event["event"] == "schedule.appointments.rejected"
    )
    assert completed["level"] == "INFO"
    assert completed["outcome"] == "completed"
    assert rejected["level"] == "WARNING"
    assert rejected["error_code"] == "invalid_or_missing_bearer_token"
    completed_request_events = [
        event for event in events if event.get("request_id") == completed_request_id
    ]
    assert [event["event"] for event in completed_request_events] == [
        "schedule.request.started",
        "schedule.reconciliation.completed",
        "schedule.allocation.completed",
        "schedule.appointments.completed",
    ]
    rejected_request_events = [
        event for event in events if event.get("request_id") == rejected_request_id
    ]
    assert [event["event"] for event in rejected_request_events] == [
        "schedule.request.started",
        "schedule.appointments.rejected",
    ]
    assert all(
        marker not in captured.err
        for marker in (
            "SECRET-SUBJECT",
            "SECRET-EXAM-CODE",
            "UNTRUSTED-REQUEST-ID-MARKER",
            JWT_SECRET,
        )
    )


def test_unexpected_service_failure_is_sanitized_in_http_and_logs(
    tmp_path, capsys
) -> None:
    class FailingScheduleService:
        def schedule(self, _subject, _exam_codes):
            raise RuntimeError("RAW-UNEXPECTED-ERROR-MARKER")

    with appointments_client(tmp_path) as client:
        client.app.dependency_overrides[get_schedule_appointments] = lambda: (
            FailingScheduleService()
        )
        response = client.post(
            "/appointments",
            headers={"Authorization": f"Bearer {access_token('user-1')}"},
            json={"exam_codes": ["CAT-001"]},
        )

    captured = capsys.readouterr()
    assert response.status_code == 500
    assert response.json() == {"detail": {"code": "schedule_unexpected_failure"}}
    assert response.headers["X-Request-ID"]
    assert "RAW-UNEXPECTED-ERROR-MARKER" not in response.text
    assert "RAW-UNEXPECTED-ERROR-MARKER" not in captured.err
    failure_event = next(
        event
        for event in map(json.loads, captured.err.splitlines())
        if event["event"] == "schedule.request.failed"
    )
    assert failure_event["request_id"] == response.headers["X-Request-ID"]


def test_openapi_documents_authentication_and_error_contracts(tmp_path) -> None:
    with appointments_client(tmp_path) as client:
        docs_response = client.get("/docs")
        schema = client.get("/openapi.json").json()

    assert docs_response.status_code == 200
    operation = schema["paths"]["/appointments"]["post"]
    assert {"200", "401", "422", "500", "503"} <= set(operation["responses"])
    assert operation["security"] == [{"HTTPBearer": []}]
    assert "CreateAppointmentsRequest" in schema["components"]["schemas"]
    assert (
        schema["components"]["schemas"]["CreateAppointmentsRequest"][
            "additionalProperties"
        ]
        is False
    )
