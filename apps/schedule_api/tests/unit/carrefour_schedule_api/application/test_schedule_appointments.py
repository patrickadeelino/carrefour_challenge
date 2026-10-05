from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from carrefour_schedule_api.application.schedule_appointments import (
    ScheduleAppointments,
)
from carrefour_schedule_api.domain.availability import AvailabilityPolicy
from carrefour_schedule_api.domain.models import AppointmentGroup

TZ = ZoneInfo("America/Sao_Paulo")
NOW = datetime(2026, 10, 5, 8, 0, tzinfo=TZ)


class InMemoryTransaction:
    def __init__(
        self,
        existing_appointments: tuple[AppointmentGroup, ...] = (),
        booked_slots: set[str] | None = None,
    ) -> None:
        self.existing_appointments = existing_appointments
        self.booked_slots = booked_slots or set()
        self.requested_codes: tuple[str, ...] = ()
        self.created_appointments: list[AppointmentGroup] = []
        self.booked_slots_read = False

    def find_appointments(
        self, user_id: str, requested_codes: tuple[str, ...], timezone: ZoneInfo
    ) -> tuple[AppointmentGroup, ...]:
        self.requested_codes = requested_codes
        return self.existing_appointments

    def booked_slots_utc(self) -> set[str]:
        self.booked_slots_read = True
        return self.booked_slots

    def create_appointment(
        self,
        *,
        appointment_id: UUID,
        user_id: str,
        scheduled_at: datetime,
        exam_codes: tuple[str, ...],
        created_at: datetime,
    ) -> AppointmentGroup:
        appointment = AppointmentGroup(
            appointment_id=appointment_id,
            scheduled_at=scheduled_at,
            exam_codes=exam_codes,
        )
        self.created_appointments.append(appointment)
        return appointment


class InMemoryRepository:
    def __init__(self, transaction: InMemoryTransaction) -> None:
        self._transaction = transaction

    @contextmanager
    def transaction(self) -> Iterator[InMemoryTransaction]:
        yield self._transaction


def make_service(transaction: InMemoryTransaction, *, horizon_days: int = 0):
    return ScheduleAppointments(
        repository=InMemoryRepository(transaction),
        availability_policy=AvailabilityPolicy(
            timezone=TZ,
            opening_time=time(9),
            closing_time=time(10),
            slot_duration_minutes=30,
            horizon_days=horizon_days,
        ),
        now_provider=lambda: NOW,
    )


def test_schedule_deduplicates_codes_preserves_order_and_reuses_existing_slot() -> None:
    existing = AppointmentGroup(
        appointment_id=UUID("00000000-0000-0000-0000-000000000001"),
        scheduled_at=datetime(2026, 10, 5, 9, 0, tzinfo=TZ),
        exam_codes=("CAT-001",),
    )
    transaction = InMemoryTransaction(
        existing_appointments=(existing,),
        booked_slots={datetime(2026, 10, 5, 12, 0, tzinfo=UTC).isoformat()},
    )

    result = make_service(transaction).schedule(
        "user-1", ["CAT-002", "CAT-001", "CAT-002", "CAT-003"]
    )

    assert result.status == "completed"
    assert result.already_scheduled == (existing,)
    assert transaction.requested_codes == ("CAT-002", "CAT-001", "CAT-003")
    assert len(transaction.created_appointments) == 1
    created = transaction.created_appointments[0]
    assert created.exam_codes == ("CAT-002", "CAT-003")
    assert created.scheduled_at == datetime(2026, 10, 5, 9, 30, tzinfo=TZ)


def test_schedule_returns_existing_appointments_without_allocating_again() -> None:
    existing = AppointmentGroup(
        appointment_id=UUID("00000000-0000-0000-0000-000000000001"),
        scheduled_at=datetime(2026, 10, 5, 9, 0, tzinfo=TZ),
        exam_codes=("CAT-001", "CAT-002"),
    )
    transaction = InMemoryTransaction(existing_appointments=(existing,))

    result = make_service(transaction).schedule("user-1", ["CAT-001", "CAT-002"])

    assert result.status == "completed"
    assert result.already_scheduled == (existing,)
    assert result.newly_scheduled == ()
    assert result.not_scheduled == ()
    assert not transaction.booked_slots_read
    assert transaction.created_appointments == []


def test_schedule_reports_new_codes_when_calendar_has_no_candidate_slots() -> None:
    saturday = datetime(2026, 10, 10, 8, 0, tzinfo=TZ)
    transaction = InMemoryTransaction()
    service = ScheduleAppointments(
        repository=InMemoryRepository(transaction),
        availability_policy=AvailabilityPolicy(
            timezone=TZ,
            opening_time=time(9),
            closing_time=time(10),
            slot_duration_minutes=30,
            horizon_days=0,
        ),
        now_provider=lambda: saturday,
    )

    result = service.schedule("user-1", ["CAT-001", "CAT-002"])

    assert result.status == "no_availability"
    assert result.already_scheduled == ()
    assert result.newly_scheduled == ()
    assert result.not_scheduled == ("CAT-001", "CAT-002")
    assert transaction.created_appointments == []


def test_schedule_rejects_naive_clock_value() -> None:
    transaction = InMemoryTransaction()
    service = ScheduleAppointments(
        repository=InMemoryRepository(transaction),
        availability_policy=AvailabilityPolicy(
            timezone=TZ,
            opening_time=time(9),
            closing_time=time(10),
            slot_duration_minutes=30,
            horizon_days=0,
        ),
        now_provider=lambda: datetime(2026, 10, 5, 8, 0),
    )

    with pytest.raises(ValueError, match="now_provider result must include a timezone"):
        service.schedule("user-1", ["CAT-001"])
