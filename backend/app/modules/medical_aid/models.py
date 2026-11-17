"""Medical aid administration: funds, patient memberships and manually tracked claims.
No electronic submission, eligibility or remittance integration exists (rule 11)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey

Money = Numeric(12, 2)


def _same_org(column: str, target: str, name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organisation_id", column], [f"{target}.organisation_id", f"{target}.id"], name=name
    )


class MedicalAidFund(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "medical_aid_funds"
    __table_args__ = (
        UniqueConstraint("organisation_id", "name"),
        UniqueConstraint("organisation_id", "id", name="uq_funds_org_id"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    administrator: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(320))
    claims_address: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class MedicalAidMembership(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "medical_aid_memberships"
    __table_args__ = (
        UniqueConstraint("organisation_id", "id", name="uq_memberships_aid_org_id"),
        _same_org("patient_id", "patients", "fk_aid_member_patient_same_org"),
        _same_org("fund_id", "medical_aid_funds", "fk_aid_member_fund_same_org"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(index=True)
    fund_id: Mapped[uuid.UUID] = mapped_column()
    plan_name: Mapped[str | None] = mapped_column(String(100))
    membership_number: Mapped[str] = mapped_column(String(50))
    dependant_code: Mapped[str | None] = mapped_column(String(10))
    principal_member_name: Mapped[str | None] = mapped_column(String(200))
    principal_member_id_number: Mapped[str | None] = mapped_column(String(50))
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_until: Mapped[date | None] = mapped_column(Date)
    # Manual verification only: unverified | verified_by_phone | verified_by_card
    verification_status: Mapped[str] = mapped_column(String(30), default="unverified")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class MedicalAidClaim(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "medical_aid_claims"
    __table_args__ = (
        UniqueConstraint("organisation_id", "claim_number"),
        UniqueConstraint("organisation_id", "id", name="uq_claims_org_id"),
        _same_org("invoice_id", "invoices", "fk_claims_invoice_same_org"),
        _same_org("patient_id", "patients", "fk_claims_patient_same_org"),
        _same_org("fund_id", "medical_aid_funds", "fk_claims_fund_same_org"),
        _same_org("membership_id", "medical_aid_memberships", "fk_claims_membership_same_org"),
        CheckConstraint("claimed_amount > 0 AND paid_amount >= 0", name="ck_claim_amounts"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    claim_number: Mapped[str] = mapped_column(String(30))
    invoice_id: Mapped[uuid.UUID] = mapped_column(index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(index=True)
    fund_id: Mapped[uuid.UUID] = mapped_column(index=True)
    membership_id: Mapped[uuid.UUID] = mapped_column()
    # Snapshot at preparation: membership details as submitted.
    membership_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # ICD-10 codes only (the minimum a fund needs); never diagnosis descriptions.
    diagnosis_codes: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=list)
    claimed_amount: Mapped[Decimal] = mapped_column(Money)
    approved_amount: Mapped[Decimal | None] = mapped_column(Money)
    paid_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(30))
    fund_reference: Mapped[str | None] = mapped_column(String(100))
    submission_method: Mapped[str | None] = mapped_column(String(30))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class ClaimEvent(UUIDPrimaryKey, Base):
    """Append-only claim history."""

    __tablename__ = "claim_events"
    __table_args__ = (
        _same_org("claim_id", "medical_aid_claims", "fk_claim_events_claim_same_org"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    claim_id: Mapped[uuid.UUID] = mapped_column(index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    previous_status: Mapped[str | None] = mapped_column(String(30))
    new_status: Mapped[str | None] = mapped_column(String(30))
    message: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
