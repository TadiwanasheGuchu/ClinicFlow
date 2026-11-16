import uuid
from datetime import date
from typing import Any

from sqlalchemy import Date, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey


class Patient(UUIDPrimaryKey, Timestamps, Base):
    """Organisation-specific patient record (demographics only; no clinical data here).

    Patient identity is never shared across organisations.
    """

    __tablename__ = "patients"
    __table_args__ = (
        UniqueConstraint("organisation_id", "patient_number"),
        UniqueConstraint("organisation_id", "id", name="uq_patients_org_id"),
        Index("ix_patients_org_last_name", "organisation_id", text("lower(last_name)")),
        Index("ix_patients_org_dob", "organisation_id", "date_of_birth"),
        Index("ix_patients_org_phone", "organisation_id", "phone"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    patient_number: Mapped[str] = mapped_column(String(20))
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    date_of_birth: Mapped[date] = mapped_column(Date)
    sex: Mapped[str | None] = mapped_column(String(20))
    nationality: Mapped[str | None] = mapped_column(String(100))
    id_number: Mapped[str | None] = mapped_column(String(50))
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(320))
    address: Mapped[str | None] = mapped_column(Text)
    emergency_contact: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    preferred_channel: Mapped[str] = mapped_column(String(20), default="sms")
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
