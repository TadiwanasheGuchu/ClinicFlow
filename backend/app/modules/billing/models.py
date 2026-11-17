"""Billing. Money is NUMERIC(12,2). Issued invoices are protected by triggers (migration
0005): totals, lines and identity never change after issue; corrections are credit notes,
refunds or payment reversals, each with its own numbered, append-only record."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey

Money = Numeric(12, 2)


def _same_org(column: str, target: str, name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organisation_id", column], [f"{target}.organisation_id", f"{target}.id"], name=name
    )


class Service(UUIDPrimaryKey, Timestamps, Base):
    """Billable service (consultation, procedure, consumable)."""

    __tablename__ = "service_catalogue"
    __table_args__ = (
        UniqueConstraint("organisation_id", "code"),
        UniqueConstraint("organisation_id", "id", name="uq_services_org_id"),
        CheckConstraint("unit_price >= 0", name="ck_service_price"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    code: Mapped[str] = mapped_column(String(30))
    # Medical aid tariff code, where one applies (entered by the practice).
    tariff_code: Mapped[str | None] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    unit_price: Mapped[Decimal] = mapped_column(Money)
    tax_category: Mapped[str] = mapped_column(String(20))  # standard | zero | exempt
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Invoice(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("organisation_id", "invoice_number"),
        UniqueConstraint("organisation_id", "id", name="uq_invoices_org_id"),
        _same_org("patient_id", "patients", "fk_invoices_patient_same_org"),
        _same_org("branch_id", "branches", "fk_invoices_branch_same_org"),
        _same_org("appointment_id", "appointments", "fk_invoices_appt_same_org"),
        CheckConstraint(
            "subtotal >= 0 AND tax_amount >= 0 AND total = subtotal + tax_amount",
            name="ck_invoice_totals",
        ),
        CheckConstraint(
            "amount_paid >= 0 AND amount_credited >= 0 AND amount_refunded >= 0 "
            "AND amount_credited <= total AND amount_refunded <= amount_paid",
            name="ck_invoice_amounts",
        ),
        Index("ix_invoices_org_patient", "organisation_id", "patient_id"),
        Index("ix_invoices_org_status", "organisation_id", "status"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    branch_id: Mapped[uuid.UUID] = mapped_column()
    patient_id: Mapped[uuid.UUID] = mapped_column()
    appointment_id: Mapped[uuid.UUID | None] = mapped_column()
    # Null while draft; assigned on issue so numbering has no gaps from discarded drafts.
    invoice_number: Mapped[str | None] = mapped_column(String(30))
    # draft | issued | partially_paid | paid | credited
    status: Mapped[str] = mapped_column(String(20))
    subtotal: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"))
    tax_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"))
    total: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"))
    amount_paid: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"))
    amount_credited: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"))
    amount_refunded: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    issued_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class InvoiceItem(UUIDPrimaryKey, Base):
    __tablename__ = "invoice_items"
    __table_args__ = (
        _same_org("invoice_id", "invoices", "fk_items_invoice_same_org"),
        _same_org("service_id", "service_catalogue", "fk_items_service_same_org"),
        CheckConstraint(
            "quantity > 0 AND unit_price >= 0 AND tax_amount >= 0", name="ck_item_amounts"
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    invoice_id: Mapped[uuid.UUID] = mapped_column(index=True)
    position: Mapped[int] = mapped_column(Integer)
    service_id: Mapped[uuid.UUID | None] = mapped_column()
    code: Mapped[str | None] = mapped_column(String(30))
    tariff_code: Mapped[str | None] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(String(300))
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    unit_price: Mapped[Decimal] = mapped_column(Money)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    line_subtotal: Mapped[Decimal] = mapped_column(Money)
    tax_amount: Mapped[Decimal] = mapped_column(Money)
    line_total: Mapped[Decimal] = mapped_column(Money)


class Payment(UUIDPrimaryKey, Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("organisation_id", "receipt_number"),
        _same_org("invoice_id", "invoices", "fk_payments_invoice_same_org"),
        _same_org("branch_id", "branches", "fk_payments_branch_same_org"),
        CheckConstraint("amount > 0", name="ck_payment_amount"),
        Index("ix_payments_org_received", "organisation_id", "received_at"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    invoice_id: Mapped[uuid.UUID] = mapped_column(index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column()
    receipt_number: Mapped[str] = mapped_column(String(30))
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3), default="NAD")
    # cash | card | eft | mobile | medical_aid. Card details are never stored.
    method: Mapped[str] = mapped_column(String(20))
    reference: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20))  # completed | reversed
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    claim_id: Mapped[uuid.UUID | None] = mapped_column()
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reversal_reason: Mapped[str | None] = mapped_column(Text)


class CreditNote(UUIDPrimaryKey, Base):
    __tablename__ = "credit_notes"
    __table_args__ = (
        UniqueConstraint("organisation_id", "credit_note_number"),
        _same_org("invoice_id", "invoices", "fk_credit_notes_invoice_same_org"),
        CheckConstraint("amount > 0", name="ck_credit_amount"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    invoice_id: Mapped[uuid.UUID] = mapped_column(index=True)
    credit_note_number: Mapped[str] = mapped_column(String(30))
    amount: Mapped[Decimal] = mapped_column(Money)
    reason: Mapped[str] = mapped_column(Text)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    issued_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class Refund(UUIDPrimaryKey, Base):
    __tablename__ = "refunds"
    __table_args__ = (
        UniqueConstraint("organisation_id", "refund_number"),
        _same_org("invoice_id", "invoices", "fk_refunds_invoice_same_org"),
        _same_org("branch_id", "branches", "fk_refunds_branch_same_org"),
        CheckConstraint("amount > 0", name="ck_refund_amount"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    invoice_id: Mapped[uuid.UUID] = mapped_column(index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column()
    refund_number: Mapped[str] = mapped_column(String(30))
    amount: Mapped[Decimal] = mapped_column(Money)
    method: Mapped[str] = mapped_column(String(20))
    reference: Mapped[str | None] = mapped_column(String(100))
    reason: Mapped[str] = mapped_column(Text)
    refunded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    refunded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
