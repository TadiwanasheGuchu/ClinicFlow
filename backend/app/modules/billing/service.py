"""Invoicing, payments, credit notes and refunds.

Balance model:
    owed       = total - amount_credited
    net_paid   = amount_paid - amount_refunded
    amount_due = owed - net_paid            (never negative: payments can't overpay)
    credit_balance = net_paid - owed        (after a credit note on a paid invoice; refundable)
Every money operation locks the invoice row (SELECT … FOR UPDATE) so concurrent payments
cannot both pass the balance check.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, NotFound, ValidationFailed
from app.core.tenancy import TenantContext, deny
from app.modules.appointments.models import Appointment
from app.modules.billing.models import CreditNote, Invoice, InvoiceItem, Payment, Refund, Service
from app.modules.organisations.schemas import OrganisationSettings
from app.modules.patients.models import Patient
from app.modules.scheduling.models import AppointmentType
from app.shared.counters import format_number, next_value

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def owed(inv: Invoice) -> Decimal:
    return inv.total - inv.amount_credited


def net_paid(inv: Invoice) -> Decimal:
    return inv.amount_paid - inv.amount_refunded


def amount_due(inv: Invoice) -> Decimal:
    return max(ZERO, owed(inv) - net_paid(inv))


def credit_balance(inv: Invoice) -> Decimal:
    return max(ZERO, net_paid(inv) - owed(inv))


def derive_status(inv: Invoice) -> str:
    if inv.status == "draft":
        return "draft"
    if owed(inv) == ZERO and inv.amount_credited > ZERO:
        return "credited"
    if net_paid(inv) >= owed(inv):
        return "paid"
    if net_paid(inv) > ZERO:
        return "partially_paid"
    return "issued"


def require_branch(ctx: TenantContext, permission: str, branch_id: uuid.UUID) -> None:
    if not ctx.has_in_branch(permission, branch_id):
        raise deny(ctx, permission, "invoice")


def get_invoice(
    db: Session, ctx: TenantContext, invoice_id: uuid.UUID, *, lock: bool = False
) -> Invoice:
    query = select(Invoice).where(Invoice.id == invoice_id)
    if lock:
        query = query.with_for_update()
    invoice = db.scalar(query)
    if invoice is None:
        raise NotFound("Invoice not found.")
    require_branch(ctx, "billing.read", invoice.branch_id)
    return invoice


def _settings(ctx: TenantContext) -> OrganisationSettings:
    return OrganisationSettings.model_validate(ctx.organisation.settings or {})


def _tax_rate(settings: OrganisationSettings, category: str) -> Decimal:
    return settings.vat_rate if settings.vat_registered and category == "standard" else ZERO


def _build_items(
    db: Session, ctx: TenantContext, invoice: Invoice, inputs: list[Any]
) -> list[InvoiceItem]:
    settings = _settings(ctx)
    items = []
    for position, data in enumerate(inputs, start=1):
        service = None
        if data.service_id is not None:
            service = db.get(Service, data.service_id)
            if service is None or not service.is_active:
                raise ValidationFailed("A selected service does not exist or is no longer offered.")
        unit_price = data.unit_price if data.unit_price is not None else service.unit_price  # type: ignore[union-attr]
        category = data.tax_category or (service.tax_category if service else "standard")
        rate = _tax_rate(settings, category)
        line_subtotal = money(data.quantity * unit_price)
        tax = money(line_subtotal * rate / 100)
        items.append(
            InvoiceItem(
                organisation_id=ctx.organisation_id,
                invoice_id=invoice.id,
                position=position,
                service_id=service.id if service else None,
                code=service.code if service else None,
                tariff_code=service.tariff_code if service else None,
                description=data.description or service.name,  # type: ignore[union-attr]
                quantity=data.quantity,
                unit_price=unit_price,
                tax_rate=rate,
                line_subtotal=line_subtotal,
                tax_amount=tax,
                line_total=line_subtotal + tax,
            )
        )
    return items


def _apply_items(db: Session, ctx: TenantContext, invoice: Invoice, inputs: list[Any]) -> None:
    db.execute(delete(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id))
    items = _build_items(db, ctx, invoice, inputs)
    db.add_all(items)
    invoice.subtotal = sum((i.line_subtotal for i in items), ZERO)
    invoice.tax_amount = sum((i.tax_amount for i in items), ZERO)
    invoice.total = invoice.subtotal + invoice.tax_amount


def create_invoice(db: Session, ctx: TenantContext, data: Any) -> Invoice:
    patient = db.get(Patient, data.patient_id)
    if patient is None:
        raise ValidationFailed("Patient not found.")
    branch_id = data.branch_id
    inputs = list(data.items)
    if data.appointment_id:
        appointment = db.get(Appointment, data.appointment_id)
        if appointment is None or appointment.patient_id != patient.id:
            raise ValidationFailed("The appointment does not belong to this patient.")
        branch_id = appointment.branch_id
        if not inputs:
            # Default line: the appointment type's fee.
            appointment_type = db.get_one(AppointmentType, appointment.appointment_type_id)
            from app.modules.billing.schemas import ItemInput

            inputs = [ItemInput(description=appointment_type.name, unit_price=appointment_type.fee)]
    require_branch(ctx, "billing.manage", branch_id)
    invoice = Invoice(
        organisation_id=ctx.organisation_id,
        branch_id=branch_id,
        patient_id=patient.id,
        appointment_id=data.appointment_id,
        status="draft",
        notes=data.notes,
        created_by=ctx.user_id,
    )
    db.add(invoice)
    db.flush()
    _apply_items(db, ctx, invoice, inputs)
    db.flush()
    ctx.audit(
        db,
        "invoice.drafted",
        "invoice",
        invoice.id,
        branch_id=branch_id,
        details={"patient_id": str(patient.id), "total": str(invoice.total)},
    )
    return invoice


def replace_items(db: Session, ctx: TenantContext, invoice: Invoice, data: Any) -> None:
    require_branch(ctx, "billing.manage", invoice.branch_id)
    if invoice.status != "draft":
        raise Conflict(
            "Issued invoices cannot be changed. Issue a credit note instead.", code="invoice_issued"
        )
    _apply_items(db, ctx, invoice, data.items)
    invoice.notes = data.notes
    db.flush()
    ctx.audit(
        db,
        "invoice.draft_updated",
        "invoice",
        invoice.id,
        branch_id=invoice.branch_id,
        details={"total": str(invoice.total)},
    )


def discard_draft(db: Session, ctx: TenantContext, invoice: Invoice) -> None:
    require_branch(ctx, "billing.manage", invoice.branch_id)
    if invoice.status != "draft":
        raise Conflict("Issued invoices cannot be deleted. Issue a credit note instead.")
    ctx.audit(db, "invoice.draft_discarded", "invoice", invoice.id, branch_id=invoice.branch_id)
    db.execute(delete(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id))
    db.delete(invoice)


def issue(db: Session, ctx: TenantContext, invoice: Invoice) -> None:
    require_branch(ctx, "billing.manage", invoice.branch_id)
    if invoice.status != "draft":
        raise Conflict("This invoice has already been issued.")
    if invoice.total <= ZERO:
        raise ValidationFailed("An invoice needs at least one line with an amount.")
    settings = _settings(ctx)
    now = datetime.now(UTC)
    invoice.invoice_number = format_number(
        settings.invoice_number_prefix, next_value(db, ctx.organisation_id, "invoice")
    )
    invoice.issued_at = now
    invoice.due_at = now + timedelta(days=settings.invoice_due_days)
    invoice.issued_by = ctx.user_id
    invoice.status = "issued"
    ctx.audit(
        db,
        "invoice.issued",
        "invoice",
        invoice.id,
        branch_id=invoice.branch_id,
        details={"number": invoice.invoice_number, "total": str(invoice.total)},
    )


def _refresh_status(invoice: Invoice) -> None:
    invoice.status = derive_status(invoice)


def record_payment(
    db: Session,
    ctx: TenantContext,
    invoice: Invoice,
    amount: Decimal,
    method: str,
    reference: str | None,
    *,
    claim_id: uuid.UUID | None = None,
) -> Payment:
    """Caller must have locked the invoice (get_invoice(..., lock=True))."""
    if invoice.status == "draft":
        raise Conflict("Issue the invoice before taking payment.")
    due = amount_due(invoice)
    if amount > due:
        raise ValidationFailed(
            f"The amount exceeds the balance due (N${due:,.2f}).",
            code="overpayment",
            details={"amount_due": str(due)},
        )
    payment = Payment(
        organisation_id=ctx.organisation_id,
        invoice_id=invoice.id,
        branch_id=invoice.branch_id,
        receipt_number=format_number("RC", next_value(db, ctx.organisation_id, "receipt")),
        amount=amount,
        method=method,
        reference=reference,
        status="completed",
        received_at=datetime.now(UTC),
        received_by=ctx.user_id,
        claim_id=claim_id,
    )
    db.add(payment)
    invoice.amount_paid += amount
    _refresh_status(invoice)
    db.flush()
    ctx.audit(
        db,
        "payment.recorded",
        "payment",
        payment.id,
        branch_id=invoice.branch_id,
        details={
            "invoice": invoice.invoice_number,
            "receipt": payment.receipt_number,
            "amount": str(amount),
            "method": method,
        },
    )
    return payment


def reverse_payment(db: Session, ctx: TenantContext, payment: Payment, reason: str) -> Invoice:
    invoice = get_invoice(db, ctx, payment.invoice_id, lock=True)
    require_branch(ctx, "billing.adjust", invoice.branch_id)
    if payment.status != "completed":
        raise Conflict("This payment has already been reversed.")
    if invoice.amount_refunded > invoice.amount_paid - payment.amount:
        raise Conflict("Refunds have been paid out against this invoice; reverse is not possible.")
    payment.status = "reversed"
    payment.reversed_at = datetime.now(UTC)
    payment.reversed_by = ctx.user_id
    payment.reversal_reason = reason
    invoice.amount_paid -= payment.amount
    _refresh_status(invoice)
    ctx.audit(
        db,
        "payment.reversed",
        "payment",
        payment.id,
        branch_id=invoice.branch_id,
        details={
            "receipt": payment.receipt_number,
            "amount": str(payment.amount),
            "reason": reason,
        },
    )
    return invoice


def credit(
    db: Session, ctx: TenantContext, invoice: Invoice, amount: Decimal, reason: str
) -> CreditNote:
    require_branch(ctx, "billing.adjust", invoice.branch_id)
    if invoice.status == "draft":
        raise Conflict("Edit the draft instead of crediting it.")
    if amount > owed(invoice):
        raise ValidationFailed(
            f"The credit exceeds the invoiced amount still owed (N${owed(invoice):,.2f})."
        )
    note = CreditNote(
        organisation_id=ctx.organisation_id,
        invoice_id=invoice.id,
        credit_note_number=format_number("CN", next_value(db, ctx.organisation_id, "credit_note")),
        amount=amount,
        reason=reason,
        issued_at=datetime.now(UTC),
        issued_by=ctx.user_id,
    )
    db.add(note)
    invoice.amount_credited += amount
    _refresh_status(invoice)
    db.flush()
    ctx.audit(
        db,
        "credit_note.issued",
        "credit_note",
        note.id,
        branch_id=invoice.branch_id,
        details={
            "invoice": invoice.invoice_number,
            "number": note.credit_note_number,
            "amount": str(amount),
        },
    )
    return note


def refund(db: Session, ctx: TenantContext, invoice: Invoice, data: Any) -> Refund:
    require_branch(ctx, "billing.adjust", invoice.branch_id)
    available = credit_balance(invoice)
    if data.amount > available:
        raise ValidationFailed(
            f"Only overpaid amounts can be refunded (N${available:,.2f} available). "
            "Issue a credit note first if the patient is owed money.",
            code="refund_exceeds_credit",
        )
    row = Refund(
        organisation_id=ctx.organisation_id,
        invoice_id=invoice.id,
        branch_id=invoice.branch_id,
        refund_number=format_number("RF", next_value(db, ctx.organisation_id, "refund")),
        amount=data.amount,
        method=data.method,
        reference=data.reference,
        reason=data.reason,
        refunded_at=datetime.now(UTC),
        refunded_by=ctx.user_id,
    )
    db.add(row)
    invoice.amount_refunded += data.amount
    _refresh_status(invoice)
    db.flush()
    ctx.audit(
        db,
        "refund.paid",
        "refund",
        row.id,
        branch_id=invoice.branch_id,
        details={
            "invoice": invoice.invoice_number,
            "number": row.refund_number,
            "amount": str(data.amount),
            "method": data.method,
        },
    )
    return row
