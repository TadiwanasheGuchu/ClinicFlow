"""Medical aid claims: prepared and tracked manually. Submission to a fund happens outside
ClinicFlow (email, fund portal, paper); staff record what happened. No electronic claim,
eligibility or remittance integration exists or is implied (rule 11)."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, NotFound, ValidationFailed
from app.core.tenancy import TenantContext
from app.modules.billing import service as billing
from app.modules.billing.models import Invoice, Payment
from app.modules.clinical.models import Diagnosis, Encounter
from app.modules.medical_aid.models import (
    ClaimEvent,
    MedicalAidClaim,
    MedicalAidFund,
    MedicalAidMembership,
)
from app.modules.patients.models import Patient
from app.shared.counters import format_number, next_value

TRANSITIONS: dict[str, set[str]] = {
    "draft": {"ready", "cancelled"},
    "ready": {"submitted", "draft", "cancelled"},
    "submitted": {"processing", "accepted", "rejected"},
    "processing": {"accepted", "rejected"},
    "accepted": set(),  # payments arrive through remittances
    "partially_paid": set(),
    "rejected": {"resubmission_required", "cancelled"},
    "resubmission_required": {"draft", "cancelled"},
    "paid": set(),
    "cancelled": set(),
}
OPEN = {
    "draft",
    "ready",
    "submitted",
    "processing",
    "accepted",
    "partially_paid",
    "rejected",
    "resubmission_required",
}


def get_claim(db: Session, claim_id: uuid.UUID, *, lock: bool = False) -> MedicalAidClaim:
    query = select(MedicalAidClaim).where(MedicalAidClaim.id == claim_id)
    if lock:
        query = query.with_for_update()
    claim = db.scalar(query)
    if claim is None:
        raise NotFound("Claim not found.")
    return claim


def _event(
    db: Session,
    ctx: TenantContext,
    claim: MedicalAidClaim,
    event_type: str,
    previous: str | None = None,
    message: str | None = None,
    details: dict | None = None,
) -> None:
    db.add(
        ClaimEvent(
            organisation_id=ctx.organisation_id,
            claim_id=claim.id,
            event_type=event_type,
            previous_status=previous,
            new_status=claim.status,
            message=message,
            details=details or {},
            actor_user_id=ctx.user_id,
            created_at=datetime.now(UTC),
        )
    )
    ctx.audit(
        db,
        f"claim.{event_type}",
        "claim",
        claim.id,
        details={"claim": claim.claim_number, "status": claim.status, **(details or {})},
    )


def _diagnosis_codes(db: Session, invoice: Invoice) -> list[str]:
    """ICD-10 codes from the consultation linked to the invoiced appointment — codes only."""
    if invoice.appointment_id is None:
        return []
    encounter = db.scalar(
        select(Encounter).where(Encounter.appointment_id == invoice.appointment_id)
    )
    if encounter is None:
        return []
    codes = db.scalars(
        select(Diagnosis.code).where(
            Diagnosis.encounter_id == encounter.id,
            Diagnosis.clinical_status != "entered_in_error",
            Diagnosis.code.is_not(None),
        )
    ).all()
    return sorted({c for c in codes if c})


def create_claim(
    db: Session, ctx: TenantContext, invoice_id: uuid.UUID, membership_id: uuid.UUID
) -> MedicalAidClaim:
    invoice = billing.get_invoice(db, ctx, invoice_id, lock=True)
    if invoice.status in ("draft", "credited"):
        raise Conflict("Only issued invoices can be claimed.")
    membership = db.get(MedicalAidMembership, membership_id)
    if membership is None or membership.patient_id != invoice.patient_id:
        raise ValidationFailed("The medical aid membership does not belong to this patient.")
    if not membership.is_active:
        raise ValidationFailed("This medical aid membership is inactive.")
    existing = db.scalar(
        select(MedicalAidClaim).where(
            MedicalAidClaim.invoice_id == invoice.id, MedicalAidClaim.status.in_(OPEN)
        )
    )
    if existing is not None:
        raise Conflict(
            f"Claim {existing.claim_number} is already open for this invoice.",
            code="claim_exists",
            details={"claim_id": str(existing.id)},
        )
    fund = db.get_one(MedicalAidFund, membership.fund_id)
    codes = _diagnosis_codes(db, invoice)
    claim = MedicalAidClaim(
        organisation_id=ctx.organisation_id,
        claim_number=format_number("CL", next_value(db, ctx.organisation_id, "claim")),
        invoice_id=invoice.id,
        patient_id=invoice.patient_id,
        fund_id=fund.id,
        membership_id=membership.id,
        membership_snapshot={
            "fund": fund.name,
            "plan": membership.plan_name,
            "membership_number": membership.membership_number,
            "dependant_code": membership.dependant_code,
            "principal_member": membership.principal_member_name,
        },
        diagnosis_codes=codes,
        claimed_amount=billing.owed(invoice) - billing.net_paid(invoice)
        if billing.amount_due(invoice) > 0
        else billing.owed(invoice),
        paid_amount=Decimal("0.00"),
        status="draft",
        created_by=ctx.user_id,
    )
    db.add(claim)
    db.flush()
    _event(
        db,
        ctx,
        claim,
        "prepared",
        details={"invoice": invoice.invoice_number, "diagnosis_codes_attached": len(codes)},
    )
    return claim


def update_draft(db: Session, ctx: TenantContext, claim: MedicalAidClaim, data: object) -> None:
    if claim.status != "draft":
        raise Conflict("Only draft claims can be edited.", code="claim_not_draft")
    invoice = db.get_one(Invoice, claim.invoice_id)
    changes = {}
    if getattr(data, "diagnosis_codes", None) is not None:
        claim.diagnosis_codes = data.diagnosis_codes  # type: ignore[attr-defined]
        changes["diagnosis_codes"] = len(claim.diagnosis_codes)
    if getattr(data, "claimed_amount", None) is not None:
        if data.claimed_amount > billing.owed(invoice):  # type: ignore[attr-defined]
            raise ValidationFailed("The claimed amount exceeds the invoice.")
        claim.claimed_amount = data.claimed_amount  # type: ignore[attr-defined]
        changes["claimed_amount"] = str(claim.claimed_amount)
    _event(db, ctx, claim, "edited", previous=claim.status, details=changes)


def transition(db: Session, ctx: TenantContext, claim: MedicalAidClaim, data: object) -> None:
    new = data.status  # type: ignore[attr-defined]
    if new not in TRANSITIONS[claim.status]:
        raise Conflict(
            f"A {claim.status.replace('_', ' ')} claim cannot become {new.replace('_', ' ')}.",
            code="invalid_transition",
        )
    now = datetime.now(UTC)
    if new == "ready":
        if not claim.diagnosis_codes:
            raise ValidationFailed(
                "Add at least one ICD-10 diagnosis code; funds require it.",
                code="diagnosis_codes_required",
            )
        if not claim.membership_snapshot.get("membership_number"):
            raise ValidationFailed("The membership number is missing.")
    if new == "submitted":
        claim.submitted_at = now
        claim.submission_method = data.submission_method  # type: ignore[attr-defined]
    if data.fund_reference:  # type: ignore[attr-defined]
        claim.fund_reference = data.fund_reference  # type: ignore[attr-defined]
    if new == "accepted":
        approved = data.approved_amount  # type: ignore[attr-defined]
        if approved > claim.claimed_amount:
            raise ValidationFailed("The approved amount cannot exceed the claimed amount.")
        claim.approved_amount = approved
        claim.response_at = now
    if new == "rejected":
        claim.rejection_reason = data.reason  # type: ignore[attr-defined]
        claim.response_at = now
    previous = claim.status
    claim.status = new
    _event(
        db,
        ctx,
        claim,
        "status_changed",
        previous=previous,
        message=data.reason,  # type: ignore[attr-defined]
        details={
            k: str(v)
            for k, v in (
                ("approved_amount", claim.approved_amount if new == "accepted" else None),
                ("fund_reference", data.fund_reference),
            )
            if v is not None
        },
    )  # type: ignore[attr-defined]


def record_remittance(
    db: Session, ctx: TenantContext, claim: MedicalAidClaim, amount: Decimal, reference: str
) -> Payment:
    if claim.status not in ("accepted", "partially_paid"):
        raise Conflict("Record payments only for accepted claims.", code="claim_not_accepted")
    outstanding = (claim.approved_amount or Decimal(0)) - claim.paid_amount
    if amount > outstanding:
        raise ValidationFailed(
            "The amount exceeds what the fund approved and has not yet paid "
            f"(N${outstanding:,.2f})."
        )
    invoice = billing.get_invoice(db, ctx, claim.invoice_id, lock=True)
    payment = billing.record_payment(
        db, ctx, invoice, amount, "medical_aid", reference, claim_id=claim.id
    )
    previous = claim.status
    claim.paid_amount += amount
    claim.status = "paid" if claim.paid_amount >= (claim.approved_amount or 0) else "partially_paid"
    _event(
        db,
        ctx,
        claim,
        "remittance_recorded",
        previous=previous,
        details={"amount": str(amount), "receipt": payment.receipt_number, "reference": reference},
    )
    return payment


def on_remittance_reversed(db: Session, ctx: TenantContext, payment: Payment) -> None:
    claim = get_claim(db, payment.claim_id, lock=True)  # type: ignore[arg-type]
    previous = claim.status
    claim.paid_amount -= payment.amount
    claim.status = "partially_paid" if claim.paid_amount > 0 else "accepted"
    _event(
        db,
        ctx,
        claim,
        "remittance_reversed",
        previous=previous,
        details={"amount": str(payment.amount), "receipt": payment.receipt_number},
    )


def patient_portion(db: Session, claim: MedicalAidClaim) -> Decimal:
    """What the patient is expected to pay towards the invoice once the fund has paid."""
    invoice = db.get_one(Invoice, claim.invoice_id)
    covered = claim.approved_amount if claim.approved_amount is not None else claim.claimed_amount
    if claim.status in ("rejected", "cancelled", "resubmission_required"):
        covered = Decimal("0.00")
    return max(Decimal("0.00"), billing.owed(invoice) - covered)


def patient_name(db: Session, patient_id: uuid.UUID) -> str:
    p = db.get_one(Patient, patient_id)
    return f"{p.first_name} {p.last_name}"
