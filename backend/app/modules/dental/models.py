"""Dental extension: tooth chart, treatment plans and quotations.

Builds on the core record (patients, consultations, the price list and invoices) without
the core depending on it. Chart entries are never edited (only marked entered in error),
and once a plan is proposed as a quotation its procedures and fees are frozen (migration
0008 triggers); only progress — done, cancelled, invoiced — can change.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey

# FDI two-digit notation: permanent quadrants 1-4 (teeth 1-8), primary quadrants 5-8 (1-5).
PERMANENT_TEETH = tuple(q * 10 + t for q in (1, 2, 3, 4) for t in range(1, 9))
PRIMARY_TEETH = tuple(q * 10 + t for q in (5, 6, 7, 8) for t in range(1, 6))
VALID_TEETH = frozenset(PERMANENT_TEETH + PRIMARY_TEETH)
SURFACES = "MODBLPI"  # mesial, occlusal, distal, buccal, lingual, palatal, incisal
CONDITIONS = (
    "sound",
    "caries",
    "filled",
    "crown",
    "root_canal",
    "missing",
    "extracted",
    "implant",
    "bridge",
    "fracture",
    "watch",
    "other",
)
_TEETH_SQL = ",".join(str(t) for t in sorted(VALID_TEETH))


def _same_org(column: str, target: str, name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organisation_id", column], [f"{target}.organisation_id", f"{target}.id"], name=name
    )


class ChartEntry(UUIDPrimaryKey, Base):
    __tablename__ = "dental_chart_entries"
    __table_args__ = (
        _same_org("patient_id", "patients", "fk_dental_chart_patient_same_org"),
        _same_org("encounter_id", "encounters", "fk_dental_chart_encounter_same_org"),
        CheckConstraint(f"tooth IN ({_TEETH_SQL})", name="ck_dental_tooth"),
        CheckConstraint("surfaces ~ '^[MODBLPI]*$'", name="ck_dental_surfaces"),
        CheckConstraint(
            "condition IN (" + ",".join(f"'{c}'" for c in CONDITIONS) + ")",
            name="ck_dental_condition",
        ),
        CheckConstraint("status IN ('recorded','entered_in_error')", name="ck_dental_chart_status"),
        Index("ix_dental_chart_org_patient", "organisation_id", "patient_id", "recorded_at"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column()
    encounter_id: Mapped[uuid.UUID] = mapped_column(index=True)
    tooth: Mapped[int] = mapped_column(SmallInteger)
    surfaces: Mapped[str] = mapped_column(String(7), default="")
    condition: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20))
    status_reason: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TreatmentPlan(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "dental_treatment_plans"
    __table_args__ = (
        UniqueConstraint("organisation_id", "plan_number"),
        UniqueConstraint("organisation_id", "id", name="uq_dental_plans_org_id"),
        _same_org("patient_id", "patients", "fk_dental_plans_patient_same_org"),
        _same_org("branch_id", "branches", "fk_dental_plans_branch_same_org"),
        CheckConstraint(
            "status IN ('draft','proposed','accepted','declined','completed','cancelled')",
            name="ck_dental_plan_status",
        ),
        Index("ix_dental_plans_org_patient", "organisation_id", "patient_id"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column()
    branch_id: Mapped[uuid.UUID] = mapped_column()
    plan_number: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    proposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quote_valid_until: Mapped[date | None] = mapped_column(Date)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # How the patient accepted or declined (e.g. "Signed quotation", "Verbal, by phone").
    decision_note: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)


class PlanItem(UUIDPrimaryKey, Base):
    __tablename__ = "dental_plan_items"
    __table_args__ = (
        UniqueConstraint("plan_id", "position"),
        _same_org("plan_id", "dental_treatment_plans", "fk_dental_items_plan_same_org"),
        _same_org("service_id", "service_catalogue", "fk_dental_items_service_same_org"),
        _same_org("done_encounter_id", "encounters", "fk_dental_items_encounter_same_org"),
        _same_org("invoice_id", "invoices", "fk_dental_items_invoice_same_org"),
        CheckConstraint(f"tooth IS NULL OR tooth IN ({_TEETH_SQL})", name="ck_dental_item_tooth"),
        CheckConstraint("surfaces ~ '^[MODBLPI]*$'", name="ck_dental_item_surfaces"),
        CheckConstraint("fee >= 0", name="ck_dental_item_fee"),
        CheckConstraint("status IN ('planned','done','cancelled')", name="ck_dental_item_status"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    plan_id: Mapped[uuid.UUID] = mapped_column(index=True)
    position: Mapped[int] = mapped_column(Integer)
    tooth: Mapped[int | None] = mapped_column(SmallInteger)
    surfaces: Mapped[str] = mapped_column(String(7), default="")
    procedure: Mapped[str] = mapped_column(String(200))
    service_id: Mapped[uuid.UUID | None] = mapped_column()
    fee: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    done_encounter_id: Mapped[uuid.UUID | None] = mapped_column()
    invoice_id: Mapped[uuid.UUID | None] = mapped_column()
