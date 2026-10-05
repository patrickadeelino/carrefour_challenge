"""Relational storage model, kept separate from domain entities."""

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base for this app's SQLAlchemy mappings."""


class AppointmentRecord(Base):
    __tablename__ = "appointments"
    __table_args__ = (UniqueConstraint("scheduled_at_utc"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    scheduled_at_utc: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at_utc: Mapped[str] = mapped_column(String(40), nullable=False)


class AppointmentExamRecord(Base):
    __tablename__ = "appointment_exams"

    appointment_id: Mapped[str] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), primary_key=True
    )
    exam_code: Mapped[str] = mapped_column(String(40), primary_key=True, index=True)
