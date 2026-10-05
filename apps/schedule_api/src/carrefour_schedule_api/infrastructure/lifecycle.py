"""Database resource startup and shutdown for the FastAPI application."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from carrefour_schedule_api.infrastructure.database import create_database_engine
from carrefour_schedule_api.infrastructure.models import Base

logger = logging.getLogger(__name__)


@asynccontextmanager
async def database_lifespan(app: FastAPI) -> AsyncIterator[None]:
    started_at = perf_counter()
    engine: Engine | None = None
    try:
        engine = create_database_engine(app.state.settings.database_path)
        Base.metadata.create_all(engine)
        app.state.engine = engine
        app.state.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    except Exception:
        if engine is not None:
            engine.dispose()
        logger.error(
            "schedule.database.failed",
            extra={
                "event_name": "schedule.database.failed",
                "component": "persistence",
                "outcome": "failed",
                "error_code": "schedule_database_initialization_failed",
                "error_type": "StartupError",
            },
        )
        raise RuntimeError("Schedule API database initialization failed") from None

    assert engine is not None
    logger.info(
        "schedule.database.ready",
        extra={
            "event_name": "schedule.database.ready",
            "component": "persistence",
            "duration_ms": max(0, int((perf_counter() - started_at) * 1000)),
            "outcome": "ready",
        },
    )
    try:
        yield
    finally:
        engine.dispose()
        logger.info(
            "schedule.database.stopped",
            extra={
                "event_name": "schedule.database.stopped",
                "component": "persistence",
                "outcome": "stopped",
            },
        )
