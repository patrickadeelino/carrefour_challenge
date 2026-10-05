from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

ScheduleStatus = Literal["completed", "partial", "no_availability"]


@dataclass(frozen=True, slots=True)
class AppointmentGroup:
    appointment_id: UUID
    scheduled_at: datetime
    exam_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScheduleResult:
    already_scheduled: tuple[AppointmentGroup, ...]
    newly_scheduled: tuple[AppointmentGroup, ...]
    not_scheduled: tuple[str, ...]

    @property
    def status(self) -> ScheduleStatus:
        if not self.not_scheduled:
            return "completed"
        if self.already_scheduled or self.newly_scheduled:
            return "partial"
        return "no_availability"
