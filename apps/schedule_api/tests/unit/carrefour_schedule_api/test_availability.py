from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from carrefour_schedule_api.domain.availability import AvailabilityPolicy

TZ = ZoneInfo("America/Sao_Paulo")


def test_candidate_slots_skip_current_slot_weekends_and_closing_boundary() -> None:
    policy = AvailabilityPolicy(
        timezone=TZ,
        opening_time=time(9),
        closing_time=time(10),
        slot_duration_minutes=30,
        horizon_days=3,
    )

    slots = list(policy.candidate_slots(datetime(2026, 10, 9, 9, 0, tzinfo=TZ)))

    assert slots == [
        datetime(2026, 10, 9, 9, 30, tzinfo=TZ),
        datetime(2026, 10, 12, 9, 0, tzinfo=TZ),
        datetime(2026, 10, 12, 9, 30, tzinfo=TZ),
    ]


@pytest.mark.parametrize(
    ("opening", "closing", "duration", "horizon"),
    [
        ("09:00", "09:00", 30, 0),
        ("10:00", "09:00", 30, 0),
        ("09:00", "10:00", 0, 0),
        ("09:00", "09:30", 31, 0),
        ("09:00", "10:00", 30, -1),
        ("09:00:01", "10:00", 30, 0),
        ("09:00+03:00", "10:00", 30, 0),
    ],
)
def test_policy_rejects_invalid_slot_configuration(
    opening: str, closing: str, duration: int, horizon: int
) -> None:
    with pytest.raises(ValueError):
        AvailabilityPolicy(
            timezone=TZ,
            opening_time=time.fromisoformat(opening),
            closing_time=time.fromisoformat(closing),
            slot_duration_minutes=duration,
            horizon_days=horizon,
        )


def test_candidate_slots_reject_naive_current_time() -> None:
    policy = AvailabilityPolicy(
        timezone=TZ,
        opening_time=time(9),
        closing_time=time(10),
        slot_duration_minutes=30,
        horizon_days=1,
    )

    with pytest.raises(ValueError, match="now must include a timezone"):
        list(policy.candidate_slots(datetime(2026, 10, 9, 8, 0)))
