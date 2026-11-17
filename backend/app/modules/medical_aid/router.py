import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import Conflict, NotFound, ValidationFailed
from app.core.tenancy import TenantContext, require
from app.modules.billing.models import Invoice
from app.modules.billing.schemas import PaymentRead
from app.modules.medical_aid import service
from app.modules.medical_aid.models import (
    ClaimEvent,
    MedicalAidClaim,
    MedicalAidFund,
    MedicalAidMembership,
)
from app.modules.medical_aid.schemas import (
    ClaimCreate,
    ClaimDetail,
    ClaimEventRead,
    ClaimRead,
    ClaimStatus,
    ClaimTransition,
    ClaimUpdate,
    FundRead,
    FundWrite,
    MembershipRead,
    MembershipVerify,
    MembershipWrite,
    Remittance,
)
from app.modules.patients.models import Patient
from app.shared.schemas import Page, PageParams

router = APIRouter(tags=["medical aid"])
DB = Annotated[Session, Depends(get_db)]
PatientReader = Annotated[TenantContext, Depends(require("patients.read"))]
PatientWriter = Annotated[TenantContext, Depends(require("patients.write"))]
FundManager = Annotated[TenantContext, Depends(require("medical_aid.manage", org_wide=True))]
ClaimReader = Annotated[TenantContext, Depends(require("billing.read"))]
ClaimManager = Annotated[TenantContext, Depends(require("medical_aid.manage"))]


# --- Funds -----------------------------------------------------------------------------


@router.get("/medical-aid/funds", response_model=list[FundRead])
def list_funds(ctx: PatientReader, db: DB, include_inactive: bool = False) -> object:
    query = select(MedicalAidFund).order_by(MedicalAidFund.name)
    if not include_inactive:
        query = query.where(MedicalAidFund.is_active.is_(True))
    return db.scalars(query).all()


@router.post("/medical-aid/funds", response_model=FundRead, status_code=status.HTTP_201_CREATED)
def create_fund(data: FundWrite, ctx: FundManager, db: DB) -> object:
    fund = MedicalAidFund(organisation_id=ctx.organisation_id, **data.model_dump())
    db.add(fund)
    try:
        db.flush()
    except IntegrityError as exc:
        raise Conflict("A fund with this name already exists.") from exc
    ctx.audit(
        db, "medical_aid_fund.created", "medical_aid_fund", fund.id, details={"name": fund.name}
    )
    db.commit()
    return fund


@router.put("/medical-aid/funds/{fund_id}", response_model=FundRead)
def update_fund(fund_id: uuid.UUID, data: FundWrite, ctx: FundManager, db: DB) -> object:
    fund = db.get(MedicalAidFund, fund_id)
    if fund is None:
        raise NotFound("Fund not found.")
    for key, value in data.model_dump().items():
        setattr(fund, key, value)
    try:
        db.flush()
    except IntegrityError as exc:
        raise Conflict("A fund with this name already exists.") from exc
    ctx.audit(
        db, "medical_aid_fund.updated", "medical_aid_fund", fund.id, details={"name": fund.name}
    )
    db.commit()
    return fund


# --- Patient memberships -----------------------------------------------------------------


def _membership_reads(db: Session, rows: list[MedicalAidMembership]) -> list[MembershipRead]:
    funds = {f.id: f.name for f in db.scalars(select(MedicalAidFund))}
    return [
        MembershipRead.model_validate(
            {
                **{k: getattr(m, k) for k in MembershipRead.model_fields if k != "fund_name"},
                "fund_name": funds.get(m.fund_id, ""),
            }
        )
        for m in rows
    ]


@router.get("/patients/{patient_id}/medical-aid", response_model=list[MembershipRead])
def list_memberships(patient_id: uuid.UUID, ctx: PatientReader, db: DB) -> object:
    if db.get(Patient, patient_id) is None:
        raise NotFound("Patient not found.")
    rows = db.scalars(
        select(MedicalAidMembership)
        .where(MedicalAidMembership.patient_id == patient_id)
        .order_by(MedicalAidMembership.is_active.desc(), MedicalAidMembership.created_at.desc())
    )
    return _membership_reads(db, list(rows))


@router.post(
    "/patients/{patient_id}/medical-aid",
    response_model=MembershipRead,
    status_code=status.HTTP_201_CREATED,
)
def add_membership(
    patient_id: uuid.UUID, data: MembershipWrite, ctx: PatientWriter, db: DB
) -> object:
    if db.get(Patient, patient_id) is None:
        raise NotFound("Patient not found.")
    fund = db.get(MedicalAidFund, data.fund_id)
    if fund is None or not fund.is_active:
        raise ValidationFailed("Choose an active medical aid fund.")
    membership = MedicalAidMembership(
        organisation_id=ctx.organisation_id,
        patient_id=patient_id,
        verification_status="unverified",
        **data.model_dump(),
    )
    db.add(membership)
    db.flush()
    ctx.audit(
        db,
        "medical_aid_membership.added",
        "patient",
        patient_id,
        details={"membership_id": str(membership.id), "fund": fund.name},
    )
    db.commit()
    return _membership_reads(db, [membership])[0]


@router.put("/medical-aid/memberships/{membership_id}", response_model=MembershipRead)
def update_membership(
    membership_id: uuid.UUID, data: MembershipWrite, ctx: PatientWriter, db: DB
) -> object:
    membership = db.get(MedicalAidMembership, membership_id)
    if membership is None:
        raise NotFound("Membership not found.")
    changed = {k for k, v in data.model_dump().items() if getattr(membership, k) != v}
    for key, value in data.model_dump().items():
        setattr(membership, key, value)
    if changed & {"fund_id", "membership_number", "dependant_code"}:
        membership.verification_status, membership.verified_at, membership.verified_by = (
            "unverified",
            None,
            None,
        )
    ctx.audit(
        db,
        "medical_aid_membership.updated",
        "patient",
        membership.patient_id,
        details={"membership_id": str(membership.id), "fields": sorted(changed)},
    )
    db.commit()
    return _membership_reads(db, [membership])[0]


@router.post("/medical-aid/memberships/{membership_id}/verify", response_model=MembershipRead)
def verify_membership(
    membership_id: uuid.UUID, data: MembershipVerify, ctx: PatientWriter, db: DB
) -> object:
    """Record a manual check (phone call to the fund or sight of the card)."""
    membership = db.get(MedicalAidMembership, membership_id)
    if membership is None:
        raise NotFound("Membership not found.")
    membership.verification_status = data.method
    membership.verified_at = datetime.now(UTC)
    membership.verified_by = ctx.user_id
    ctx.audit(
        db,
        "medical_aid_membership.verified",
        "patient",
        membership.patient_id,
        details={"membership_id": str(membership.id), "method": data.method, "note": data.note},
    )
    db.commit()
    return _membership_reads(db, [membership])[0]


# --- Claims --------------------------------------------------------------------------------


def _claim_reads(db: Session, rows: list[MedicalAidClaim]) -> list[ClaimRead]:
    if not rows:
        return []
    funds = {
        f.id: f.name
        for f in db.scalars(
            select(MedicalAidFund).where(MedicalAidFund.id.in_({c.fund_id for c in rows}))
        )
    }
    invoices = {
        i.id: i.invoice_number
        for i in db.scalars(select(Invoice).where(Invoice.id.in_({c.invoice_id for c in rows})))
    }
    patients = {
        p.id: f"{p.first_name} {p.last_name}"
        for p in db.scalars(select(Patient).where(Patient.id.in_({c.patient_id for c in rows})))
    }
    return [
        ClaimRead.model_validate(
            {
                **{
                    k: getattr(c, k)
                    for k in ClaimRead.model_fields
                    if k not in ("fund_name", "invoice_number", "patient_name", "patient_portion")
                },
                "fund_name": funds.get(c.fund_id, ""),
                "invoice_number": invoices.get(c.invoice_id),
                "patient_name": patients.get(c.patient_id, ""),
                "patient_portion": service.patient_portion(db, c),
            }
        )
        for c in rows
    ]


def _detail(db: Session, claim: MedicalAidClaim) -> ClaimDetail:
    events = db.scalars(
        select(ClaimEvent).where(ClaimEvent.claim_id == claim.id).order_by(ClaimEvent.created_at)
    )
    return ClaimDetail(
        **_claim_reads(db, [claim])[0].model_dump(),
        events=[ClaimEventRead.model_validate(e) for e in events],
    )


@router.get("/claims", response_model=Page[ClaimRead])
def list_claims(
    ctx: ClaimReader,
    db: DB,
    page: Annotated[PageParams, Depends()],
    status_filter: Annotated[list[ClaimStatus] | None, Query(alias="status")] = None,
    fund_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
    invoice_id: uuid.UUID | None = None,
) -> object:
    query = select(MedicalAidClaim)
    if status_filter:
        query = query.where(MedicalAidClaim.status.in_(status_filter))
    for column, value in (
        (MedicalAidClaim.fund_id, fund_id),
        (MedicalAidClaim.patient_id, patient_id),
        (MedicalAidClaim.invoice_id, invoice_id),
    ):
        if value:
            query = query.where(column == value)
    scope = ctx.branch_scope("billing.read")
    if scope is not None:
        query = query.where(
            MedicalAidClaim.invoice_id.in_(select(Invoice.id).where(Invoice.branch_id.in_(scope)))
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(MedicalAidClaim.created_at.desc()).limit(page.limit).offset(page.offset)
    ).all()
    return Page(
        items=_claim_reads(db, list(rows)), total=total, limit=page.limit, offset=page.offset
    )


def _claim_for(
    db: Session, ctx: TenantContext, claim_id: uuid.UUID, permission: str, *, lock: bool = False
) -> MedicalAidClaim:
    claim = service.get_claim(db, claim_id, lock=lock)
    invoice = db.get_one(Invoice, claim.invoice_id)
    if not ctx.has_in_branch(permission, invoice.branch_id):
        from app.core.tenancy import deny

        raise deny(ctx, permission, "claim")
    return claim


@router.get("/claims/{claim_id}", response_model=ClaimDetail)
def read_claim(claim_id: uuid.UUID, ctx: ClaimReader, db: DB) -> object:
    return _detail(db, _claim_for(db, ctx, claim_id, "billing.read"))


@router.post("/claims", response_model=ClaimDetail, status_code=status.HTTP_201_CREATED)
def create_claim(data: ClaimCreate, ctx: ClaimManager, db: DB) -> object:
    claim = service.create_claim(db, ctx, data.invoice_id, data.membership_id)
    db.commit()
    return _detail(db, claim)


@router.patch("/claims/{claim_id}", response_model=ClaimDetail)
def edit_claim(claim_id: uuid.UUID, data: ClaimUpdate, ctx: ClaimManager, db: DB) -> object:
    claim = _claim_for(db, ctx, claim_id, "medical_aid.manage", lock=True)
    service.update_draft(db, ctx, claim, data)
    db.commit()
    return _detail(db, claim)


@router.post("/claims/{claim_id}/status", response_model=ClaimDetail)
def change_status(claim_id: uuid.UUID, data: ClaimTransition, ctx: ClaimManager, db: DB) -> object:
    claim = _claim_for(db, ctx, claim_id, "medical_aid.manage", lock=True)
    service.transition(db, ctx, claim, data)
    db.commit()
    return _detail(db, claim)


@router.post(
    "/claims/{claim_id}/remittance", response_model=PaymentRead, status_code=status.HTTP_201_CREATED
)
def remittance(claim_id: uuid.UUID, data: Remittance, ctx: ClaimManager, db: DB) -> object:
    claim = _claim_for(db, ctx, claim_id, "medical_aid.manage", lock=True)
    payment = service.record_remittance(db, ctx, claim, data.amount, data.reference)
    db.commit()
    return payment
