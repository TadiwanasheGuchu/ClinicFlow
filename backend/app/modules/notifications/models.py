import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey


class Notification(UUIDPrimaryKey, Timestamps, Base):
    """Outbox of patient messages. Rendered at enqueue time from an allowlist of
    non-clinical fields; the worker only delivers ``body`` to ``recipient``."""

    __tablename__ = "notifications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organisation_id", "patient_id"],
            ["patients.organisation_id", "patients.id"],
            name="fk_notifications_patient_same_org",
        ),
        ForeignKeyConstraint(
            ["organisation_id", "appointment_id"],
            ["appointments.organisation_id", "appointments.id"],
            name="fk_notifications_appt_same_org",
        ),
        Index("ix_notifications_due", "delivery_status", "scheduled_for"),
        Index("ix_notifications_org_created", "organisation_id", "created_at"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    patient_id: Mapped[uuid.UUID | None] = mapped_column()
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    event_type: Mapped[str] = mapped_column(String(50))
    channel: Mapped[str] = mapped_column(String(20))  # sms | whatsapp | email
    recipient: Mapped[str | None] = mapped_column(String(320))
    subject: Mapped[str | None] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    # pending | sending | sent | failed | cancelled | skipped
    delivery_status: Mapped[str] = mapped_column(String(20))
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    provider_reference: Mapped[str | None] = mapped_column(String(200))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
