"""Ports used by scheduling use cases to access appointment persistence."""

from contextlib import AbstractContextManager
from datetime import datetime
from typing import Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from carrefour_schedule_api.domain.models import AppointmentGroup


class AppointmentTransaction(Protocol):
    def find_appointments(
        self, user_id: str, requested_codes: tuple[str, ...], timezone: ZoneInfo
    ) -> tuple[AppointmentGroup, ...]: ...

    def booked_slots_utc(self) -> set[str]: ...

    def create_appointment(
        self,
        *,
        appointment_id: UUID,
        user_id: str,
        scheduled_at: datetime,
        exam_codes: tuple[str, ...],
        created_at: datetime,
    ) -> AppointmentGroup: ...


class AppointmentRepository(Protocol):
    def transaction(self) -> AbstractContextManager[AppointmentTransaction]: ...
