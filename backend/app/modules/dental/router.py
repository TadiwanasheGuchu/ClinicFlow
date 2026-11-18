import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import NotFound
from app.core.tenancy import TenantContext, require
from app.modules.clinical import service as clinical
from app.modules.clinical.models import Encounter
from app.modules.dental import service
from app.modules.dental.models import TreatmentPlan
from app.modules.dental.schemas import (
    ChartBatch,
    DentalChart,
    InvoiceRef,
    ItemDone,
    PlanDecision,
    PlanRead,
    PlanWrite,
    Propose,
    Reason,
)

router = APIRouter(tags=["dental"])
DB = Annotated[Session, Depends(get_db)]


def _gated(permission: str):  # type: ignore[no-untyped-def]
    base = require(permission)

    def dependency(ctx: Annotated[TenantContext, Depends(base)]) -> TenantContext:
        service.gate(ctx)
        return ctx

    return dependency


Reader = Annotated[TenantContext, Depends(_gated("clinical.read"))]
Writer = Annotated[TenantContext, Depends(_gated("clinical.write"))]


@router.get("/patients/{patient_id}/dental-chart", response_model=DentalChart)
def chart(patient_id: uuid.UUID, ctx: Reader, db: DB) -> object:
    patient = clinical.get_patient(db, patient_id)
    result = service.chart(db, ctx, patient.id)
    clinical.log_view(db, ctx, patient.id, "dental_chart")
    db.commit()
    return result


@router.post(
    "/encounters/{encounter_id}/dental-chart",
    response_model=DentalChart,
    status_code=status.HTTP_201_CREATED,
)
def record(encounter_id: uuid.UUID, data: ChartBatch, ctx: Writer, db: DB) -> object:
    encounter = db.get(Encounter, encounter_id)
    if encounter is None:
        raise NotFound("Consultation not found.")
    service.record_chart(db, ctx, encounter, data)
    db.commit()
    return service.chart(db, ctx, encounter.patient_id)


@router.post("/dental-chart/{entry_id}/entered-in-error", response_model=DentalChart)
def chart_error(entry_id: uuid.UUID, data: Reason, ctx: Writer, db: DB) -> object:
    entry = service.chart_entry_error(db, ctx, entry_id, data.reason)
    db.commit()
    return service.chart(db, ctx, entry.patient_id)


@router.get("/patients/{patient_id}/dental-plans", response_model=list[PlanRead])
def list_plans(patient_id: uuid.UUID, ctx: Reader, db: DB) -> object:
    patient = clinical.get_patient(db, patient_id)
    query = select(TreatmentPlan).where(TreatmentPlan.patient_id == patient.id)
    scope = ctx.branch_scope("clinical.read")
    if scope is not None:
        query = query.where(TreatmentPlan.branch_id.in_(scope))
    rows = list(db.scalars(query.order_by(TreatmentPlan.created_at.desc())))
    clinical.log_view(db, ctx, patient.id, "dental_plans")
    db.commit()
    return service.plan_reads(db, rows)


@router.post("/dental-plans", response_model=PlanRead, status_code=status.HTTP_201_CREATED)
def create_plan(data: PlanWrite, ctx: Writer, db: DB) -> object:
    plan = service.save_plan(db, ctx, None, data)
    db.commit()
    return service.plan_reads(db, [plan])[0]


@router.get("/dental-plans/{plan_id}", response_model=PlanRead)
def read_plan(plan_id: uuid.UUID, ctx: Reader, db: DB) -> object:
    plan = service.get_plan(db, ctx, plan_id)
    clinical.log_view(db, ctx, plan.patient_id, "dental_plan", plan.id)
    db.commit()
    return service.plan_reads(db, [plan])[0]


@router.put("/dental-plans/{plan_id}", response_model=PlanRead)
def update_plan(plan_id: uuid.UUID, data: PlanWrite, ctx: Writer, db: DB) -> object:
    plan = service.save_plan(db, ctx, service.get_plan(db, ctx, plan_id, lock=True), data)
    db.commit()
    return service.plan_reads(db, [plan])[0]


@router.post("/dental-plans/{plan_id}/propose", response_model=PlanRead)
def propose(plan_id: uuid.UUID, data: Propose, ctx: Writer, db: DB) -> object:
    plan = service.get_plan(db, ctx, plan_id, lock=True)
    service.propose(db, ctx, plan, data.valid_days)
    db.commit()
    return service.plan_reads(db, [plan])[0]


@router.post("/dental-plans/{plan_id}/decide", response_model=PlanRead)
def decide(plan_id: uuid.UUID, data: PlanDecision, ctx: Writer, db: DB) -> object:
    plan = service.get_plan(db, ctx, plan_id, lock=True)
    service.decide(db, ctx, plan, data.decision, data.note)
    db.commit()
    return service.plan_reads(db, [plan])[0]


@router.post("/dental-plans/{plan_id}/items/{item_id}/done", response_model=PlanRead)
def item_done(
    plan_id: uuid.UUID, item_id: uuid.UUID, data: ItemDone, ctx: Writer, db: DB
) -> object:
    plan = service.get_plan(db, ctx, plan_id, lock=True)
    service.item_done(db, ctx, plan, item_id, data.encounter_id)
    db.commit()
    return service.plan_reads(db, [plan])[0]


@router.post("/dental-plans/{plan_id}/items/{item_id}/cancel", response_model=PlanRead)
def item_cancel(plan_id: uuid.UUID, item_id: uuid.UUID, ctx: Writer, db: DB) -> object:
    plan = service.get_plan(db, ctx, plan_id, lock=True)
    service.item_cancel(db, ctx, plan, item_id)
    db.commit()
    return service.plan_reads(db, [plan])[0]


@router.post("/dental-plans/{plan_id}/cancel", response_model=PlanRead)
def cancel(plan_id: uuid.UUID, data: Reason, ctx: Writer, db: DB) -> object:
    plan = service.get_plan(db, ctx, plan_id, lock=True)
    service.cancel(db, ctx, plan, data.reason)
    db.commit()
    return service.plan_reads(db, [plan])[0]


@router.post("/dental-plans/{plan_id}/invoice", response_model=InvoiceRef)
def invoice(plan_id: uuid.UUID, ctx: Writer, db: DB) -> object:
    plan = service.get_plan(db, ctx, plan_id, lock=True)
    invoice_id, count = service.invoice_done(db, ctx, plan)
    db.commit()
    return InvoiceRef(invoice_id=invoice_id, items=count)
