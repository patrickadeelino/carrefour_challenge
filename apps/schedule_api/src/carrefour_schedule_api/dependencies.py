"""FastAPI dependencies for per-request SQLAlchemy units of work."""

from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from carrefour_schedule_api.application.schedule_appointments import (
    ScheduleAppointments,
)
from carrefour_schedule_api.infrastructure.sqlite_repository import (
    SQLiteAppointmentRepository,
)


def get_session(request: Request) -> Iterator[Session]:
    """Yield one session per request and close it before sending the response."""
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


SessionDep = Annotated[Session, Depends(get_session, scope="function")]


def get_schedule_appointments(
    request: Request, session: SessionDep
) -> ScheduleAppointments:
    return ScheduleAppointments(
        repository=SQLiteAppointmentRepository(session),
        availability_policy=request.app.state.availability_policy,
        now_provider=cast(Callable[[], datetime], request.app.state.now_provider),
    )


ScheduleAppointmentsDep = Annotated[
    ScheduleAppointments, Depends(get_schedule_appointments)
]
