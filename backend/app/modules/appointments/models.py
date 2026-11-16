import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey


def _same_org(column: str, target: str, name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organisation_id", column],
        [f"{target}.organisation_id", f"{target}.id"],
        name=name,
    )


class Appointment(UUIDPrimaryKey, Timestamps, Base):
    """A booking. Overlaps for the same provider or patient are rejected by database
    exclusion constraints (see migration 0002) unless an authorised override is recorded.

    ``blocked_until`` = end_at + the appointment type's buffer; the provider is busy until then.
    """

    __tablename__ = "appointments"
    __table_args__ = (
        UniqueConstraint("organisation_id", "reference"),
        UniqueConstraint("organisation_id", "id", name="uq_appointments_org_id"),
        CheckConstraint("start_at < end_at AND end_at <= blocked_until", name="ck_appt_times"),
        _same_org("branch_id", "branches", "fk_appt_branch_same_org"),
        _same_org("patient_id", "patients", "fk_appt_patient_same_org"),
        _same_org("provider_id", "providers", "fk_appt_provider_same_org"),
        _same_org("appointment_type_id", "appointment_types", "fk_appt_type_same_org"),
        Index("ix_appt_org_provider_start", "organisation_id", "provider_id", "start_at"),
        Index("ix_appt_org_branch_start", "organisation_id", "branch_id", "start_at"),
        Index("ix_appt_org_patient_start", "organisation_id", "patient_id", "start_at"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    reference: Mapped[str] = mapped_column(String(20))
    branch_id: Mapped[uuid.UUID] = mapped_column()
    patient_id: Mapped[uuid.UUID] = mapped_column()
    provider_id: Mapped[uuid.UUID] = mapped_column()
    appointment_type_id: Mapped[uuid.UUID] = mapped_column()
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    blocked_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30))
    booking_source: Mapped[str] = mapped_column(String(20))
    # Administrative note only (e.g. "prefers morning"). Never clinical information.
    booking_note: Mapped[str | None] = mapped_column(Text)
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    # Set when an authorised user overrode a scheduling rule; such rows are exempt
    # from the overlap constraints.
    is_override: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class AppointmentEvent(UUIDPrimaryKey, Base):
    """Append-only history of every appointment change."""

    __tablename__ = "appointment_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organisation_id", "appointment_id"],
            ["appointments.organisation_id", "appointments.id"],
            name="fk_appt_events_appt_same_org",
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    appointment_id: Mapped[uuid.UUID] = mapped_column(index=True)
    event_type: Mapped[str] = mapped_column(String(50))
    previous_status: Mapped[str | None] = mapped_column(String(30))
    new_status: Mapped[str | None] = mapped_column(String(30))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column()
    reason: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), server_default=func.now()
    )
