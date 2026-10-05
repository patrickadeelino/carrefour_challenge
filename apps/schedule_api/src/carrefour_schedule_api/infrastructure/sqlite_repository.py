"""Session-bound repository for appointment allocation and reconciliation."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from carrefour_schedule_api.domain.models import AppointmentGroup
from carrefour_schedule_api.domain.temporal import require_timezone_aware
from carrefour_schedule_api.infrastructure.models import (
    AppointmentExamRecord,
    AppointmentRecord,
)


class SQLiteAppointmentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @contextmanager
    def transaction(self) -> Iterator["SQLiteAppointmentTransaction"]:
        with self._session.begin():
            yield SQLiteAppointmentTransaction(self._session)


class SQLiteAppointmentTransaction:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_appointments(
        self, user_id: str, requested_codes: tuple[str, ...], timezone: ZoneInfo
    ) -> tuple[AppointmentGroup, ...]:
        if not requested_codes:
            return ()

        statement = (
            select(
                AppointmentRecord.id,
                AppointmentRecord.scheduled_at_utc,
                AppointmentExamRecord.exam_code,
            )
            .join(
                AppointmentExamRecord,
                AppointmentExamRecord.appointment_id == AppointmentRecord.id,
            )
            .where(
                AppointmentRecord.user_id == user_id,
                AppointmentExamRecord.exam_code.in_(requested_codes),
            )
            .order_by(AppointmentRecord.scheduled_at_utc)
        )
        rows = self._session.execute(statement).all()
        request_order = {code: index for index, code in enumerate(requested_codes)}
        groups: dict[str, tuple[str, list[str]]] = {}
        for appointment_id, scheduled_at_utc, exam_code in rows:
            group = groups.setdefault(str(appointment_id), (str(scheduled_at_utc), []))
            group[1].append(str(exam_code))

        return tuple(
            AppointmentGroup(
                appointment_id=UUID(appointment_id),
                scheduled_at=require_timezone_aware(
                    datetime.fromisoformat(scheduled_at_utc),
                    field_name="scheduled_at_utc",
                ).astimezone(timezone),
                exam_codes=tuple(sorted(codes, key=request_order.__getitem__)),
            )
            for appointment_id, (scheduled_at_utc, codes) in groups.items()
        )

    def booked_slots_utc(self) -> set[str]:
        statement = select(AppointmentRecord.scheduled_at_utc)
        return {str(value) for value in self._session.scalars(statement)}

    def create_appointment(
        self,
        *,
        appointment_id: UUID,
        user_id: str,
        scheduled_at: datetime,
        exam_codes: tuple[str, ...],
        created_at: datetime,
    ) -> AppointmentGroup:
        scheduled_at = require_timezone_aware(scheduled_at, field_name="scheduled_at")
        created_at = require_timezone_aware(created_at, field_name="created_at")
        scheduled_at_utc = scheduled_at.astimezone(UTC).isoformat()
        self._session.add(
            AppointmentRecord(
                id=str(appointment_id),
                user_id=user_id,
                scheduled_at_utc=scheduled_at_utc,
                created_at_utc=created_at.astimezone(UTC).isoformat(),
            )
        )
        self._session.flush()
        self._session.add_all(
            [
                AppointmentExamRecord(
                    appointment_id=str(appointment_id), exam_code=code
                )
                for code in exam_codes
            ]
        )
        self._session.flush()
        return AppointmentGroup(
            appointment_id=appointment_id,
            scheduled_at=scheduled_at,
            exam_codes=exam_codes,
        )
