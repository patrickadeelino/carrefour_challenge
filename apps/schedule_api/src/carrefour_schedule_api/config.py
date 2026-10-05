import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True, slots=True)
class ScheduleApiSettings:
    database_path: Path
    jwt_secret: str
    timezone: ZoneInfo = ZoneInfo("America/Sao_Paulo")
    opening_time: time = time(9, 0)
    closing_time: time = time(17, 0)
    slot_duration_minutes: int = 30
    horizon_days: int = 30
    enable_demo_token_issuer: bool = False

    def __post_init__(self) -> None:
        if len(self.jwt_secret.encode("utf-8")) < 32:
            raise ValueError("CARREFOUR_SCHEDULE_JWT_SECRET must be at least 32 bytes")

    @classmethod
    def from_environment(cls) -> "ScheduleApiSettings":
        jwt_secret = os.environ.get("CARREFOUR_SCHEDULE_JWT_SECRET")
        if jwt_secret is None:
            raise RuntimeError("CARREFOUR_SCHEDULE_JWT_SECRET is required")

        timezone_name = os.environ.get(
            "CARREFOUR_SCHEDULE_TIMEZONE", "America/Sao_Paulo"
        )
        try:
            timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as error:
            raise ValueError("CARREFOUR_SCHEDULE_TIMEZONE is invalid") from error

        return cls(
            database_path=Path(
                os.environ.get(
                    "CARREFOUR_SCHEDULE_DATABASE_PATH",
                    "/var/lib/carrefour/schedule/appointments.sqlite3",
                )
            ),
            jwt_secret=jwt_secret,
            timezone=timezone,
            opening_time=_parse_time("CARREFOUR_SCHEDULE_OPENING_TIME", "09:00"),
            closing_time=_parse_time("CARREFOUR_SCHEDULE_CLOSING_TIME", "17:00"),
            slot_duration_minutes=_parse_integer(
                "CARREFOUR_SCHEDULE_SLOT_DURATION_MINUTES", 30
            ),
            horizon_days=_parse_integer("CARREFOUR_SCHEDULE_HORIZON_DAYS", 30),
            enable_demo_token_issuer=_parse_boolean(
                "CARREFOUR_SCHEDULE_ENABLE_DEMO_TOKEN_ISSUER", False
            ),
        )


def _parse_time(variable: str, default: str) -> time:
    value = os.environ.get(variable, default)
    try:
        parsed = time.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{variable} must use HH:MM format") from error
    if parsed.isoformat(timespec="minutes") != value:
        raise ValueError(f"{variable} must use HH:MM format")
    return parsed


def _parse_integer(variable: str, default: int) -> int:
    try:
        return int(os.environ.get(variable, str(default)))
    except ValueError as error:
        raise ValueError(f"{variable} must be an integer") from error


def _parse_boolean(variable: str, default: bool) -> bool:
    value = os.environ.get(variable)
    if value is None:
        return default
    normalized = value.lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise ValueError(f"{variable} must be a boolean")
