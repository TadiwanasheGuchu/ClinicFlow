"""Laboratory orders and results (manual workflow; no laboratory system is integrated).

Database triggers (migration 0006) keep the record trustworthy: order items and status
events are append-only, results can only be marked "entered in error" (never edited or
deleted), and an order's identity can never change or be deleted.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey

ORDER_STATUSES = (
    "requested",
    "collected",
    "sent",
    "processing",
    "completed",
    "reviewed",
    "cancelled",
)
RESULT_FLAGS = ("normal", "low", "high", "critical_low", "critical_high", "abnormal", "none")


def _same_org(column: str, target: str, name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organisation_id", column], [f"{target}.organisation_id", f"{target}.id"], name=name
    )


class Laboratory(UUIDPrimaryKey, Timestamps, Base):
    """An external laboratory the practice sends specimens to."""

    __tablename__ = "laboratories"
    __table_args__ = (
        UniqueConstraint("organisation_id", "name"),
        UniqueConstraint("organisation_id", "id", name="uq_laboratories_org_id"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(254))
    notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class LabTest(UUIDPrimaryKey, Timestamps, Base):
    """The practice's list of orderable tests (a picking list; orders keep a snapshot)."""

    __tablename__ = "laboratory_tests"
    __table_args__ = (
        UniqueConstraint("organisation_id", "code"),
        UniqueConstraint("organisation_id", "id", name="uq_lab_tests_org_id"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    code: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(100))
    specimen_type: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class LabOrder(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "laboratory_orders"
    __table_args__ = (
        UniqueConstraint("organisation_id", "order_number"),
        UniqueConstraint("organisation_id", "id", name="uq_lab_orders_org_id"),
        _same_org("encounter_id", "encounters", "fk_lab_orders_encounter_same_org"),
        _same_org("patient_id", "patients", "fk_lab_orders_patient_same_org"),
        _same_org("branch_id", "branches", "fk_lab_orders_branch_same_org"),
        _same_org("laboratory_id", "laboratories", "fk_lab_orders_lab_same_org"),
        CheckConstraint(
            "status IN ('requested','collected','sent','processing','completed','reviewed',"
            "'cancelled')",
            name="ck_lab_order_status",
        ),
        CheckConstraint("urgency IN ('routine','urgent')", name="ck_lab_order_urgency"),
        Index("ix_lab_orders_org_status", "organisation_id", "status", "requested_at"),
        Index("ix_lab_orders_org_patient", "organisation_id", "patient_id", "requested_at"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    branch_id: Mapped[uuid.UUID] = mapped_column()
    patient_id: Mapped[uuid.UUID] = mapped_column()
    encounter_id: Mapped[uuid.UUID] = mapped_column(index=True)
    order_number: Mapped[str] = mapped_column(String(20))
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    laboratory_id: Mapped[uuid.UUID | None] = mapped_column()
    urgency: Mapped[str] = mapped_column(String(10))
    # Clinical details for the laboratory (printed on the request form).
    clinical_information: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    # The laboratory's own reference (accession number), once known.
    external_reference: Mapped[str | None] = mapped_column(String(100))
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    review_comment: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)


class LabOrderItem(UUIDPrimaryKey, Base):
    """One requested test. A snapshot: later catalogue changes don't alter past orders."""

    __tablename__ = "laboratory_order_items"
    __table_args__ = (
        UniqueConstraint("organisation_id", "id", name="uq_lab_items_org_id"),
        UniqueConstraint("order_id", "position"),
        _same_org("order_id", "laboratory_orders", "fk_lab_items_order_same_org"),
        _same_org("test_id", "laboratory_tests", "fk_lab_items_test_same_org"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    order_id: Mapped[uuid.UUID] = mapped_column(index=True)
    position: Mapped[int] = mapped_column(Integer)
    test_id: Mapped[uuid.UUID | None] = mapped_column()
    test_code: Mapped[str | None] = mapped_column(String(30))
    test_name: Mapped[str] = mapped_column(String(200))
    specimen_type: Mapped[str | None] = mapped_column(String(100))


class LabResult(UUIDPrimaryKey, Base):
    """One reported value. A panel (e.g. full blood count) has a result per analyte."""

    __tablename__ = "laboratory_results"
    __table_args__ = (
        _same_org("order_id", "laboratory_orders", "fk_lab_results_order_same_org"),
        _same_org("item_id", "laboratory_order_items", "fk_lab_results_item_same_org"),
        CheckConstraint(
            "flag IN ('normal','low','high','critical_low','critical_high','abnormal','none')",
            name="ck_lab_result_flag",
        ),
        CheckConstraint("status IN ('final','entered_in_error')", name="ck_lab_result_status"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    order_id: Mapped[uuid.UUID] = mapped_column(index=True)
    item_id: Mapped[uuid.UUID] = mapped_column(index=True)
    analyte: Mapped[str] = mapped_column(String(200))
    value: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str | None] = mapped_column(String(40))
    reference_range: Mapped[str | None] = mapped_column(String(100))
    flag: Mapped[str] = mapped_column(String(20))
    comment: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    status_reason: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LabOrderEvent(UUIDPrimaryKey, Base):
    """Append-only history of an order's status changes."""

    __tablename__ = "laboratory_order_events"
    __table_args__ = (_same_org("order_id", "laboratory_orders", "fk_lab_events_order_same_org"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    order_id: Mapped[uuid.UUID] = mapped_column(index=True)
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)
