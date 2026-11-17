import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey


class OrganisationSlug(Base):
    """Public portal address -> organisation. Deliberately outside RLS: it holds only the
    public slug, so anonymous portal visitors can resolve which practice they are visiting."""

    __tablename__ = "organisation_slugs"

    slug: Mapped[str] = mapped_column(String(60), primary_key=True)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), unique=True)


class PatientAccount(UUIDPrimaryKey, Timestamps, Base):
    """Links a sign-in identity to one patient record in one organisation."""

    __tablename__ = "patient_accounts"
    __table_args__ = (
        UniqueConstraint("organisation_id", "user_id"),
        UniqueConstraint("organisation_id", "patient_id"),
        ForeignKeyConstraint(
            ["organisation_id", "patient_id"],
            ["patients.organisation_id", "patients.id"],
            name="fk_patient_accounts_patient_same_org",
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    linked_via: Mapped[str] = mapped_column(String(20))  # registration | code
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | revoked


class PatientLinkCode(UUIDPrimaryKey, Base):
    """One-time code reception gives a patient to connect their account to an existing
    record. Only a hash is stored."""

    __tablename__ = "patient_link_codes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organisation_id", "patient_id"],
            ["patients.organisation_id", "patients.id"],
            name="fk_link_codes_patient_same_org",
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(index=True)
    code_hash: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
