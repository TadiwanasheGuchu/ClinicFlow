import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import Conflict, NotFound
from app.core.tenancy import TenantContext, TenantDep, deny, require
from app.modules.billing import service
from app.modules.billing.models import CreditNote, Invoice, InvoiceItem, Payment, Refund, Service
from app.modules.billing.schemas import (
    CashUp,
    CashUpMethod,
    CreditInput,
    CreditNoteRead,
    InvoiceCreate,
    InvoiceItemsReplace,
    InvoiceRead,
    InvoiceSummary,
    ItemRead,
    PaymentInput,
    PaymentRead,
    Reason,
    RefundInput,
    RefundRead,
    ServiceRead,
    ServiceWrite,
    Statement,
    StatementLine,
)
from app.modules.medical_aid.models import MedicalAidClaim
from app.modules.patients.models import Patient
from app.shared.schemas import Page, PageParams

router = APIRouter(tags=["billing"])
DB = Annotated[Session, Depends(get_db)]
Reader = Annotated[TenantContext, Depends(require("billing.read"))]


def _price_list_reader(ctx: TenantDep) -> TenantContext:
    """Clinicians quote from the price list (e.g. dental treatment plans); it's not sensitive."""
    if not (ctx.has("billing.read") or ctx.has("clinical.write")):
        raise deny(ctx, "billing.read")
    return ctx


PriceListReader = Annotated[TenantContext, Depends(_price_list_reader)]
Manager = Annotated[TenantContext, Depends(require("billing.manage"))]
Adjuster = Annotated[TenantContext, Depends(require("billing.adjust"))]
# Prices are set by billing staff and owners, not the front desk.
CatalogueManager = Annotated[TenantContext, Depends(require("billing.adjust", org_wide=True))]


# --- Service catalogue ----------------------------------------------------------------


@router.get("/services", response_model=list[ServiceRead])
def list_services(ctx: PriceListReader, db: DB, include_inactive: bool = False) -> object:
    query = select(Service).order_by(Service.name)
    if not include_inactive:
        query = query.where(Service.is_active.is_(True))
    return db.scalars(query).all()


@router.post("/services", response_model=ServiceRead, status_code=status.HTTP_201_CREATED)
def create_service(data: ServiceWrite, ctx: CatalogueManager, db: DB) -> object:
    item = Service(organisation_id=ctx.organisation_id, **data.model_dump())
    db.add(item)
    try:
        db.flush()
    except IntegrityError as exc:
        raise Conflict("A service with this code already exists.") from exc
    ctx.audit(db, "service.created", "service", item.id, details=data.model_dump(mode="json"))
    db.commit()
    return item


@router.put("/services/{service_id}", response_model=ServiceRead)
def update_service(
    service_id: uuid.UUID, data: ServiceWrite, ctx: CatalogueManager, db: DB
) -> object:
    item = db.get(Service, service_id)
    if item is None:
        raise NotFound("Service not found.")
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    try:
        db.flush()
    except IntegrityError as exc:
        raise Conflict("A service with this code already exists.") from exc
    ctx.audit(db, "service.updated", "service", item.id, details=data.model_dump(mode="json"))
    db.commit()
    return item


# --- Invoices ----------------------------------------------------------------------------


def _summaries(db: Session, rows: list[Invoice]) -> list[InvoiceSummary]:
    patients = (
        {
            p.id: p
            for p in db.scalars(select(Patient).where(Patient.id.in_({r.patient_id for r in rows})))
        }
        if rows
        else {}
    )
    return [
        InvoiceSummary(
            id=r.id,
            invoice_number=r.invoice_number,
            status=r.status,
            patient_id=r.patient_id,
            patient_name=f"{patients[r.patient_id].first_name} {patients[r.patient_id].last_name}",
            patient_number=patients[r.patient_id].patient_number,
            branch_id=r.branch_id,
            appointment_id=r.appointment_id,
            total=r.total,
            amount_due=service.amount_due(r),
            issued_at=r.issued_at,
            due_at=r.due_at,
            created_at=r.created_at,
        )
        for r in rows
    ]


def invoice_read(db: Session, invoice: Invoice) -> InvoiceRead:
    def rows(model, order):  # type: ignore[no-untyped-def]
        return list(db.scalars(select(model).where(model.invoice_id == invoice.id).order_by(order)))

    claims = [
        {
            "id": str(c.id),
            "claim_number": c.claim_number,
            "status": c.status,
            "claimed_amount": str(c.claimed_amount),
            "approved_amount": str(c.approved_amount) if c.approved_amount is not None else None,
            "paid_amount": str(c.paid_amount),
        }
        for c in rows(MedicalAidClaim, MedicalAidClaim.created_at)
    ]
    return InvoiceRead(
        **_summaries(db, [invoice])[0].model_dump(),
        subtotal=invoice.subtotal,
        tax_amount=invoice.tax_amount,
        amount_paid=invoice.amount_paid,
        amount_credited=invoice.amount_credited,
        amount_refunded=invoice.amount_refunded,
        credit_balance=service.credit_balance(invoice),
        notes=invoice.notes,
        items=[ItemRead.model_validate(i) for i in rows(InvoiceItem, InvoiceItem.position)],
        payments=[PaymentRead.model_validate(p) for p in rows(Payment, Payment.received_at)],
        credit_notes=[
            CreditNoteRead.model_validate(c) for c in rows(CreditNote, CreditNote.issued_at)
        ],
        refunds=[RefundRead.model_validate(r) for r in rows(Refund, Refund.refunded_at)],
        claims=claims,
    )


@router.get("/invoices", response_model=Page[InvoiceSummary])
def list_invoices(
    ctx: Reader,
    db: DB,
    page: Annotated[PageParams, Depends()],
    patient_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    appointment_id: uuid.UUID | None = None,
    status_filter: Annotated[
        Literal["draft", "issued", "partially_paid", "paid", "credited", "outstanding"] | None,
        Query(alias="status"),
    ] = None,
    q: Annotated[str | None, Query(max_length=50)] = None,
) -> object:
    query = select(Invoice)
    for column, value in (
        (Invoice.patient_id, patient_id),
        (Invoice.branch_id, branch_id),
        (Invoice.appointment_id, appointment_id),
    ):
        if value:
            query = query.where(column == value)
    if status_filter == "outstanding":
        query = query.where(Invoice.status.in_(("issued", "partially_paid")))
    elif status_filter:
        query = query.where(Invoice.status == status_filter)
    if q:
        query = query.where(
            or_(
                func.upper(Invoice.invoice_number) == q.strip().upper(),
                Invoice.patient_id.in_(
                    select(Patient.id).where(
                        or_(
                            Patient.last_name.ilike(f"{q.strip()}%"),
                            func.upper(Patient.patient_number) == q.strip().upper(),
                        )
                    )
                ),
            )
        )
    scope = ctx.branch_scope("billing.read")
    if scope is not None:
        query = query.where(Invoice.branch_id.in_(scope))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(Invoice.created_at.desc()).limit(page.limit).offset(page.offset)
    ).all()
    return Page(items=_summaries(db, list(rows)), total=total, limit=page.limit, offset=page.offset)


@router.post("/invoices", response_model=InvoiceRead, status_code=status.HTTP_201_CREATED)
def create_invoice(data: InvoiceCreate, ctx: Manager, db: DB) -> object:
    invoice = service.create_invoice(db, ctx, data)
    db.commit()
    return invoice_read(db, invoice)


@router.get("/invoices/{invoice_id}", response_model=InvoiceRead)
def read_invoice(invoice_id: uuid.UUID, ctx: Reader, db: DB) -> object:
    return invoice_read(db, service.get_invoice(db, ctx, invoice_id))


@router.put("/invoices/{invoice_id}/items", response_model=InvoiceRead)
def replace_items(invoice_id: uuid.UUID, data: InvoiceItemsReplace, ctx: Manager, db: DB) -> object:
    invoice = service.get_invoice(db, ctx, invoice_id, lock=True)
    service.replace_items(db, ctx, invoice, data)
    db.commit()
    return invoice_read(db, invoice)


@router.delete("/invoices/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
def discard_invoice(invoice_id: uuid.UUID, ctx: Manager, db: DB) -> Response:
    service.discard_draft(db, ctx, service.get_invoice(db, ctx, invoice_id, lock=True))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/invoices/{invoice_id}/issue", response_model=InvoiceRead)
def issue_invoice(invoice_id: uuid.UUID, ctx: Manager, db: DB) -> object:
    invoice = service.get_invoice(db, ctx, invoice_id, lock=True)
    service.issue(db, ctx, invoice)
    db.commit()
    return invoice_read(db, invoice)


@router.post(
    "/invoices/{invoice_id}/payments",
    response_model=PaymentRead,
    status_code=status.HTTP_201_CREATED,
)
def take_payment(invoice_id: uuid.UUID, data: PaymentInput, ctx: Manager, db: DB) -> object:
    invoice = service.get_invoice(db, ctx, invoice_id, lock=True)
    service.require_branch(ctx, "billing.manage", invoice.branch_id)
    payment = service.record_payment(db, ctx, invoice, data.amount, data.method, data.reference)
    db.commit()
    return payment


@router.get("/payments/{payment_id}", response_model=PaymentRead)
def read_payment(payment_id: uuid.UUID, ctx: Reader, db: DB) -> object:
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise NotFound("Payment not found.")
    service.require_branch(ctx, "billing.read", payment.branch_id)
    return payment


@router.post("/payments/{payment_id}/reverse", response_model=InvoiceRead)
def reverse_payment(payment_id: uuid.UUID, data: Reason, ctx: Adjuster, db: DB) -> object:
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise NotFound("Payment not found.")
    invoice = service.reverse_payment(db, ctx, payment, data.reason)
    if payment.claim_id:
        from app.modules.medical_aid import service as medical_aid

        medical_aid.on_remittance_reversed(db, ctx, payment)
    db.commit()
    return invoice_read(db, invoice)


@router.post(
    "/invoices/{invoice_id}/credit-notes",
    response_model=InvoiceRead,
    status_code=status.HTTP_201_CREATED,
)
def credit_invoice(invoice_id: uuid.UUID, data: CreditInput, ctx: Adjuster, db: DB) -> object:
    invoice = service.get_invoice(db, ctx, invoice_id, lock=True)
    service.credit(db, ctx, invoice, data.amount, data.reason)
    db.commit()
    return invoice_read(db, invoice)


@router.post(
    "/invoices/{invoice_id}/refunds",
    response_model=InvoiceRead,
    status_code=status.HTTP_201_CREATED,
)
def refund_invoice(invoice_id: uuid.UUID, data: RefundInput, ctx: Adjuster, db: DB) -> object:
    invoice = service.get_invoice(db, ctx, invoice_id, lock=True)
    service.refund(db, ctx, invoice, data)
    db.commit()
    return invoice_read(db, invoice)


# --- Statements and cash-up ------------------------------------------------------------


@router.get("/patients/{patient_id}/statement", response_model=Statement)
def statement(patient_id: uuid.UUID, ctx: Reader, db: DB) -> object:
    if db.get(Patient, patient_id) is None:
        raise NotFound("Patient not found.")
    invoices = list(
        db.scalars(
            select(Invoice).where(Invoice.patient_id == patient_id, Invoice.status != "draft")
        )
    )
    scope = ctx.branch_scope("billing.read")
    if scope is not None:
        invoices = [i for i in invoices if i.branch_id in scope]
    ids = [i.id for i in invoices]
    numbers = {i.id: i.invoice_number or "" for i in invoices}
    events: list[tuple[datetime, str, str, str, Decimal, Decimal]] = []
    for i in invoices:
        events.append(
            (i.issued_at, "invoice", i.invoice_number or "", "Invoice", i.total, Decimal(0))
        )  # type: ignore[arg-type]
    for p in db.scalars(select(Payment).where(Payment.invoice_id.in_(ids))):
        label = "Medical aid payment" if p.method == "medical_aid" else f"Payment ({p.method})"
        events.append(
            (
                p.received_at,
                "payment",
                p.receipt_number,
                f"{label} · {numbers[p.invoice_id]}",
                Decimal(0),
                p.amount,
            )
        )
        if p.status == "reversed":
            events.append(
                (
                    p.reversed_at,
                    "payment_reversed",
                    p.receipt_number,
                    f"Payment reversed · {numbers[p.invoice_id]}",
                    p.amount,
                    Decimal(0),
                )
            )  # type: ignore[arg-type]
    for c in db.scalars(select(CreditNote).where(CreditNote.invoice_id.in_(ids))):
        events.append(
            (
                c.issued_at,
                "credit_note",
                c.credit_note_number,
                f"Credit note · {numbers[c.invoice_id]}",
                Decimal(0),
                c.amount,
            )
        )
    for r in db.scalars(select(Refund).where(Refund.invoice_id.in_(ids))):
        events.append(
            (
                r.refunded_at,
                "refund",
                r.refund_number,
                f"Refund ({r.method}) · {numbers[r.invoice_id]}",
                r.amount,
                Decimal(0),
            )
        )
    events.sort(key=lambda e: e[0])
    balance = Decimal("0.00")
    lines = []
    for when, kind, ref, desc, debit, credit_amount in events:
        balance += debit - credit_amount
        lines.append(
            StatementLine(
                date=when,
                kind=kind,
                reference=ref,
                description=desc,  # type: ignore[arg-type]
                debit=debit,
                credit=credit_amount,
                balance=balance,
            )
        )
    return Statement(patient_id=patient_id, lines=lines, balance=balance)


@router.get("/billing/cash-up", response_model=CashUp)
def cash_up(
    ctx: Reader,
    db: DB,
    day: Annotated[date, Query(alias="date")],
    branch_id: uuid.UUID | None = None,
) -> object:
    """Money received and refunded on a local calendar day (organisation timezone)."""
    tz = ZoneInfo(ctx.organisation.timezone)
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    scope = ctx.branch_scope("billing.read")
    if branch_id is not None:
        service.require_branch(ctx, "billing.read", branch_id)

    def scoped(query, column):  # type: ignore[no-untyped-def]
        if branch_id is not None:
            return query.where(column == branch_id)
        if scope is not None:
            return query.where(column.in_(scope))
        return query

    payments = list(
        db.scalars(
            scoped(
                select(Payment).where(Payment.received_at >= start, Payment.received_at < end),
                Payment.branch_id,
            ).order_by(Payment.received_at)
        )
    )
    refunds = list(
        db.scalars(
            scoped(
                select(Refund).where(Refund.refunded_at >= start, Refund.refunded_at < end),
                Refund.branch_id,
            )
        )
    )
    methods: dict[str, CashUpMethod] = {}
    for p in payments:
        if p.status != "completed":
            continue
        m = methods.setdefault(
            p.method,
            CashUpMethod(
                method=p.method,
                count=0,
                received=Decimal("0.00"),
                refunded=Decimal("0.00"),
                net=Decimal("0.00"),
            ),
        )
        m.count += 1
        m.received += p.amount
    for r in refunds:
        m = methods.setdefault(
            r.method,
            CashUpMethod(
                method=r.method,
                count=0,
                received=Decimal("0.00"),
                refunded=Decimal("0.00"),
                net=Decimal("0.00"),
            ),
        )
        m.refunded += r.amount
    for m in methods.values():
        m.net = m.received - m.refunded
    received = sum((m.received for m in methods.values()), Decimal("0.00"))
    refunded = sum((m.refunded for m in methods.values()), Decimal("0.00"))
    return CashUp(
        date=day.isoformat(),
        branch_id=branch_id,
        by_method=sorted(methods.values(), key=lambda m: m.method),
        total_received=received,
        total_refunded=refunded,
        net=received - refunded,
        reversed_payments=[
            PaymentRead.model_validate(p) for p in payments if p.status == "reversed"
        ],
        payments=[PaymentRead.model_validate(p) for p in payments],
    )
