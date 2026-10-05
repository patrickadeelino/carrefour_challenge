from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from carrefour_schedule_api.domain.temporal import require_timezone_aware


@dataclass(frozen=True, slots=True)
class AvailabilityPolicy:
    timezone: ZoneInfo
    opening_time: time
    closing_time: time
    slot_duration_minutes: int
    horizon_days: int

    def __post_init__(self) -> None:
        if any(
            value.second or value.microsecond or value.tzinfo is not None
            for value in (self.opening_time, self.closing_time)
        ):
            raise ValueError("working hours must use local HH:MM without seconds")
        if self.opening_time >= self.closing_time:
            raise ValueError("opening_time must be earlier than closing_time")
        if self.slot_duration_minutes <= 0:
            raise ValueError("slot_duration_minutes must be positive")
        if self.horizon_days < 0:
            raise ValueError("horizon_days cannot be negative")
        available_minutes = (
            self.closing_time.hour * 60
            + self.closing_time.minute
            - self.opening_time.hour * 60
            - self.opening_time.minute
        )
        if self.slot_duration_minutes > available_minutes:
            raise ValueError("slot_duration_minutes must fit within working hours")

    def candidate_slots(self, now: datetime) -> Iterator[datetime]:
        local_now = require_timezone_aware(now, field_name="now").astimezone(
            self.timezone
        )
        duration = timedelta(minutes=self.slot_duration_minutes)

        for day_offset in range(self.horizon_days + 1):
            day = local_now.date() + timedelta(days=day_offset)
            if day.weekday() >= 5:
                continue

            slot_start = datetime.combine(day, self.opening_time, self.timezone)
            closing_at = datetime.combine(day, self.closing_time, self.timezone)
            while slot_start + duration <= closing_at:
                if slot_start > local_now:
                    yield slot_start
                slot_start += duration
