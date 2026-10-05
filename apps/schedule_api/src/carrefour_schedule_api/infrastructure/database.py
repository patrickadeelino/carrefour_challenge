"""SQLAlchemy engine setup for the file-backed SQLite database."""

from pathlib import Path

from sqlalchemy import URL, Engine, create_engine, event
from sqlalchemy.engine import Connection
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.pool import ConnectionPoolEntry


def create_database_engine(database_path: Path) -> Engine:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        URL.create("sqlite", database=str(database_path)),
        connect_args={"check_same_thread": False, "timeout": 10},
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite_connection(
        connection: DBAPIConnection, _record: ConnectionPoolEntry
    ) -> None:
        connection.isolation_level = None
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA busy_timeout = 10000")
        cursor.close()

    @event.listens_for(engine, "begin")
    def begin_immediate(connection: Connection) -> None:
        connection.exec_driver_sql("BEGIN IMMEDIATE")

    return engine
