import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from carrefour_schedule_api.application.ports import (
    AppointmentRepository,
    AppointmentTransaction,
)
from carrefour_schedule_api.domain.availability import AvailabilityPolicy
from carrefour_schedule_api.domain.models import AppointmentGroup, ScheduleResult
from carrefour_schedule_api.domain.temporal import require_timezone_aware

logger = logging.getLogger(__name__)


class ScheduleAppointments:
    def __init__(
        self,
        *,
        repository: AppointmentRepository,
        availability_policy: AvailabilityPolicy,
        now_provider: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._availability_policy = availability_policy
        self._now_provider = now_provider

    def schedule(self, user_id: str, exam_codes: list[str]) -> ScheduleResult:
        distinct_codes = tuple(dict.fromkeys(exam_codes))
        now = require_timezone_aware(
            self._now_provider(), field_name="now_provider result"
        )
        timezone = self._availability_policy.timezone

        with self._repository.transaction() as transaction:
            existing = transaction.find_appointments(user_id, distinct_codes, timezone)
            new_codes = self._new_exam_codes(distinct_codes, existing)
            logger.info(
                "schedule.reconciliation.completed",
                extra={
                    "event_name": "schedule.reconciliation.completed",
                    "component": "application",
                    "outcome": "completed",
                },
            )
            result = self._allocate_new_exams(
                transaction=transaction,
                user_id=user_id,
                exam_codes=new_codes,
                existing_appointments=existing,
                now=now,
            )

        allocation_outcome = self._allocation_outcome(new_codes, result)
        logger.info(
            "schedule.allocation.completed",
            extra={
                "event_name": "schedule.allocation.completed",
                "component": "application",
                "outcome": allocation_outcome,
            },
        )
        return result

    @staticmethod
    def _new_exam_codes(
        exam_codes: tuple[str, ...], existing: tuple[AppointmentGroup, ...]
    ) -> tuple[str, ...]:
        scheduled_codes = {
            code for appointment in existing for code in appointment.exam_codes
        }
        return tuple(code for code in exam_codes if code not in scheduled_codes)

    def _allocate_new_exams(
        self,
        *,
        transaction: AppointmentTransaction,
        user_id: str,
        exam_codes: tuple[str, ...],
        existing_appointments: tuple[AppointmentGroup, ...],
        now: datetime,
    ) -> ScheduleResult:
        if not exam_codes:
            return ScheduleResult(existing_appointments, (), ())

        available_slot = self._find_available_slot(transaction, now)
        if available_slot is None:
            return ScheduleResult(existing_appointments, (), exam_codes)

        new_appointment = transaction.create_appointment(
            appointment_id=uuid4(),
            user_id=user_id,
            scheduled_at=available_slot,
            exam_codes=exam_codes,
            created_at=now,
        )
        return ScheduleResult(existing_appointments, (new_appointment,), ())

    def _find_available_slot(
        self, transaction: AppointmentTransaction, now: datetime
    ) -> datetime | None:
        booked_slots = transaction.booked_slots_utc()
        return next(
            (
                slot
                for slot in self._availability_policy.candidate_slots(now)
                if slot.astimezone(UTC).isoformat() not in booked_slots
            ),
            None,
        )

    @staticmethod
    def _allocation_outcome(new_codes: tuple[str, ...], result: ScheduleResult) -> str:
        if not new_codes:
            return "not_required"
        if result.not_scheduled:
            return "no_availability"
        return "allocated"
