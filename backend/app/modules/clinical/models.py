"""Clinical records. Signed notes and issued prescriptions are protected by database
triggers (migration 0004): content can never change after signing; corrections are new
versions (notes) or cancellations (prescriptions), and nothing signed can be deleted."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey


def _same_org(column: str, target: str, name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organisation_id", column], [f"{target}.organisation_id", f"{target}.id"], name=name
    )


class Encounter(UUIDPrimaryKey, Timestamps, Base):
    """A consultation or other clinical contact."""

    __tablename__ = "encounters"
    __table_args__ = (
        UniqueConstraint("organisation_id", "id", name="uq_encounters_org_id"),
        UniqueConstraint("appointment_id", name="uq_encounters_appointment"),
        _same_org("patient_id", "patients", "fk_encounters_patient_same_org"),
        _same_org("branch_id", "branches", "fk_encounters_branch_same_org"),
        _same_org("appointment_id", "appointments", "fk_encounters_appt_same_org"),
        Index("ix_encounters_org_patient", "organisation_id", "patient_id", "started_at"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    branch_id: Mapped[uuid.UUID] = mapped_column()
    patient_id: Mapped[uuid.UUID] = mapped_column()
    appointment_id: Mapped[uuid.UUID | None] = mapped_column()
    encounter_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20))  # open | closed
    clinician_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClinicalNote(UUIDPrimaryKey, Timestamps, Base):
    """One version of a note. Versions of the same note share ``note_group_id``."""

    __tablename__ = "clinical_notes"
    __table_args__ = (
        UniqueConstraint("note_group_id", "version_number", name="uq_note_version"),
        _same_org("encounter_id", "encounters", "fk_notes_encounter_same_org"),
        _same_org("patient_id", "patients", "fk_notes_patient_same_org"),
        CheckConstraint("status IN ('draft','signed','amended')", name="ck_note_status"),
        CheckConstraint("(status = 'draft') = (signed_at IS NULL)", name="ck_note_signed_fields"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    encounter_id: Mapped[uuid.UUID] = mapped_column(index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(index=True)
    note_group_id: Mapped[uuid.UUID] = mapped_column(index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    # draft -> signed; a signed version becomes "amended" when a later version is signed.
    status: Mapped[str] = mapped_column(String(20))
    note_type: Mapped[str] = mapped_column(String(30))
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    author_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    amends_note_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clinical_notes.id"))
    amendment_reason: Mapped[str | None] = mapped_column(Text)


class Allergy(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "allergies"
    __table_args__ = (_same_org("patient_id", "patients", "fk_allergies_patient_same_org"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(index=True)
    substance: Mapped[str] = mapped_column(String(200))
    reaction: Mapped[str | None] = mapped_column(String(500))
    severity: Mapped[str] = mapped_column(String(20))  # mild|moderate|severe|unknown
    status: Mapped[str] = mapped_column(String(20))  # active|inactive|entered_in_error
    status_reason: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class AllergyAssessment(Base):
    """Explicit 'no known allergies' statement, so a blank allergy list is never ambiguous."""

    __tablename__ = "allergy_assessments"
    __table_args__ = (_same_org("patient_id", "patients", "fk_allergy_assess_patient_same_org"),)

    patient_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    no_known_allergies: Mapped[bool] = mapped_column()
    recorded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Observation(UUIDPrimaryKey, Base):
    __tablename__ = "observations"
    __table_args__ = (
        _same_org("encounter_id", "encounters", "fk_obs_encounter_same_org"),
        _same_org("patient_id", "patients", "fk_obs_patient_same_org"),
        Index("ix_obs_org_patient_type", "organisation_id", "patient_id", "observation_type"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    encounter_id: Mapped[uuid.UUID] = mapped_column(index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column()
    observation_type: Mapped[str] = mapped_column(String(40))
    value: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    unit: Mapped[str] = mapped_column(String(20))
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20))  # final | entered_in_error
    status_reason: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class Diagnosis(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "diagnoses"
    __table_args__ = (
        _same_org("encounter_id", "encounters", "fk_dx_encounter_same_org"),
        _same_org("patient_id", "patients", "fk_dx_patient_same_org"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    encounter_id: Mapped[uuid.UUID] = mapped_column(index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(index=True)
    code_system: Mapped[str] = mapped_column(String(20))  # icd10 | none
    code: Mapped[str | None] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(String(500))
    clinical_status: Mapped[str] = mapped_column(String(20))  # active|resolved|entered_in_error
    status_reason: Mapped[str | None] = mapped_column(Text)
    onset_date: Mapped[date | None] = mapped_column(Date)
    recorded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class Referral(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "referrals"
    __table_args__ = (
        _same_org("encounter_id", "encounters", "fk_ref_encounter_same_org"),
        _same_org("patient_id", "patients", "fk_ref_patient_same_org"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    encounter_id: Mapped[uuid.UUID] = mapped_column(index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(index=True)
    referring_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    receiving_provider: Mapped[str] = mapped_column(String(200))
    receiving_specialty: Mapped[str | None] = mapped_column(String(100))
    urgency: Mapped[str] = mapped_column(String(20))  # routine | urgent
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))  # issued | cancelled
    status_reason: Mapped[str | None] = mapped_column(Text)


class Prescription(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "prescriptions"
    __table_args__ = (
        UniqueConstraint("organisation_id", "prescription_number"),
        UniqueConstraint("organisation_id", "id", name="uq_prescriptions_org_id"),
        _same_org("encounter_id", "encounters", "fk_rx_encounter_same_org"),
        _same_org("patient_id", "patients", "fk_rx_patient_same_org"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    encounter_id: Mapped[uuid.UUID] = mapped_column(index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(index=True)
    prescription_number: Mapped[str] = mapped_column(String(20))
    prescriber_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    # Snapshot of the prescriber's registration at issue time (printed on the document).
    prescriber_name: Mapped[str] = mapped_column(String(200))
    prescriber_registration: Mapped[str] = mapped_column(String(150))
    status: Mapped[str] = mapped_column(String(20))  # issued | cancelled
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    allergy_warning: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class PrescriptionItem(UUIDPrimaryKey, Base):
    __tablename__ = "prescription_items"
    __table_args__ = (_same_org("prescription_id", "prescriptions", "fk_rx_items_rx_same_org"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    prescription_id: Mapped[uuid.UUID] = mapped_column(index=True)
    position: Mapped[int] = mapped_column(Integer)
    medication: Mapped[str] = mapped_column(String(200))
    strength: Mapped[str | None] = mapped_column(String(50))
    dosage_form: Mapped[str | None] = mapped_column(String(50))
    dose: Mapped[str] = mapped_column(String(100))
    frequency: Mapped[str] = mapped_column(String(100))
    route: Mapped[str | None] = mapped_column(String(50))
    duration: Mapped[str | None] = mapped_column(String(50))
    quantity: Mapped[str | None] = mapped_column(String(50))
    instructions: Mapped[str | None] = mapped_column(Text)
