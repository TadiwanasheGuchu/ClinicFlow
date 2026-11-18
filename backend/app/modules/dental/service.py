"""Dental extension service.

Uses the core permissions (credential-gated): clinical.read to view, clinical.write to
chart and plan, both checked in the patient's branch. Invoicing completed treatment goes
through the billing service, which also requires billing.manage. Audit entries carry
identifiers, counts and totals only — never teeth, conditions or procedures.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, NotFound, ValidationFailed
from app.core.tenancy import TenantContext
from app.modules.billing import service as billing
from app.modules.billing.models import Service
from app.modules.billing.schemas import InvoiceCreate, ItemInput
from app.modules.clinical import service as clinical
from app.modules.clinical.models import Encounter
from app.modules.dental.models import ChartEntry, PlanItem, TreatmentPlan
from app.modules.dental.schemas import (
    ChartBatch,
    ChartEntryRead,
    DentalChart,
    PlanItemRead,
    PlanRead,
    PlanWrite,
)
from app.shared.counters import format_number, next_value
from app.shared.modules import require_module

MODULE = "dental"
ZERO = Decimal("0.00")


def gate(ctx: TenantContext) -> None:
    require_module(ctx, MODULE)


# --- Chart -------------------------------------------------------------------------------


def record_chart(db: Session, ctx: TenantContext, encounter: Encounter, batch: ChartBatch) -> int:
    clinical.open_for_writing(ctx, encounter)
    now = datetime.now(UTC)
    db.add_all(
        ChartEntry(
            organisation_id=ctx.organisation_id,
            patient_id=encounter.patient_id,
            encounter_id=encounter.id,
            tooth=e.tooth,
            surfaces=e.surfaces,
            condition=e.condition,
            note=e.note or None,
            status="recorded",
            recorded_by=ctx.user_id,
            recorded_at=now,
        )
        for e in batch.entries
    )
    db.flush()
    ctx.audit(
        db,
        "dental_chart.recorded",
        "patient",
        encounter.patient_id,
        branch_id=encounter.branch_id,
        details={"encounter_id": str(encounter.id), "entries": len(batch.entries)},
    )
    return len(batch.entries)


def chart_entry_error(
    db: Session, ctx: TenantContext, entry_id: uuid.UUID, reason: str
) -> ChartEntry:
    entry = db.get(ChartEntry, entry_id, with_for_update=True)
    if entry is None:
        raise NotFound("Chart entry not found.")
    encounter = db.get_one(Encounter, entry.encounter_id)
    clinical.require_in_branch(ctx, "clinical.write", encounter.branch_id)
    if entry.status != "recorded":
        raise Conflict("This entry is already marked as entered in error.")
    entry.status, entry.status_reason = "entered_in_error", reason
    ctx.audit(
        db,
        "dental_chart.entered_in_error",
        "patient",
        entry.patient_id,
        branch_id=encounter.branch_id,
        details={"entry_id": str(entry.id)},
    )
    return entry


def chart(db: Session, ctx: TenantContext, patient_id: uuid.UUID) -> DentalChart:
    query = (
        select(ChartEntry)
        .join(Encounter, Encounter.id == ChartEntry.encounter_id)
        .where(ChartEntry.patient_id == patient_id)
    )
    scope = ctx.branch_scope("clinical.read")
    if scope is not None:
        query = query.where(Encounter.branch_id.in_(scope))
    rows = list(db.scalars(query.order_by(ChartEntry.recorded_at.desc(), ChartEntry.id)))
    names = clinical.user_names(db, {r.recorded_by for r in rows})
    reads = [
        ChartEntryRead.model_validate(
            {
                **{
                    k: getattr(r, k) for k in ChartEntryRead.model_fields if k != "recorded_by_name"
                },
                "recorded_by_name": names.get(r.recorded_by, ""),
            }
        )
        for r in rows
    ]
    teeth: dict[int, list[ChartEntryRead]] = {}
    for r in reads:
        if r.status == "recorded":
            teeth.setdefault(r.tooth, []).append(r)
    return DentalChart(patient_id=patient_id, teeth=teeth, history=reads)


# --- Treatment plans and quotations ------------------------------------------------------


def get_plan(
    db: Session, ctx: TenantContext, plan_id: uuid.UUID, *, lock: bool = False
) -> TreatmentPlan:
    plan = db.get(TreatmentPlan, plan_id, with_for_update=lock or None)
    if plan is None:
        raise NotFound("Treatment plan not found.")
    clinical.require_in_branch(ctx, "clinical.read", plan.branch_id)
    return plan


def _items(db: Session, plan_id: uuid.UUID) -> list[PlanItem]:
    return list(
        db.scalars(select(PlanItem).where(PlanItem.plan_id == plan_id).order_by(PlanItem.position))
    )


def _write_items(db: Session, ctx: TenantContext, plan: TreatmentPlan, data: PlanWrite) -> None:
    for item in _items(db, plan.id):
        db.delete(item)
    db.flush()
    for position, entry in enumerate(data.items, start=1):
        procedure, fee = entry.procedure, entry.fee
        if entry.service_id is not None:
            service = db.get(Service, entry.service_id)
            if service is None or not service.is_active:
                raise ValidationFailed("A chosen service is not on the active price list.")
            procedure = procedure or service.name
            fee = service.unit_price if fee is None else fee
        if not procedure or fee is None:
            raise ValidationFailed("Each item needs a procedure and a fee, or a service.")
        db.add(
            PlanItem(
                organisation_id=ctx.organisation_id,
                plan_id=plan.id,
                position=position,
                tooth=entry.tooth,
                surfaces=entry.surfaces,
                procedure=procedure,
                service_id=entry.service_id,
                fee=billing.money(Decimal(fee)),
                status="planned",
            )
        )
    db.flush()


def save_plan(
    db: Session, ctx: TenantContext, plan: TreatmentPlan | None, data: PlanWrite
) -> TreatmentPlan:
    clinical.require_in_branch(ctx, "clinical.write", data.branch_id)
    patient = clinical.get_patient(db, data.patient_id)
    if plan is None:
        plan = TreatmentPlan(
            organisation_id=ctx.organisation_id,
            patient_id=patient.id,
            plan_number=format_number("TP", next_value(db, ctx.organisation_id, "dental_plan")),
            status="draft",
            created_by=ctx.user_id,
        )
        db.add(plan)
        action = "dental_plan.created"
    else:
        clinical.require_in_branch(ctx, "clinical.write", plan.branch_id)
        if plan.status != "draft":
            raise Conflict(
                "A quoted plan can't be changed; cancel it and start a new one.",
                code="plan_not_draft",
            )
        if plan.patient_id != patient.id:
            raise ValidationFailed("A plan can't be moved to another patient.")
        action = "dental_plan.updated"
    plan.branch_id, plan.title, plan.notes = data.branch_id, data.title, data.notes or None
    db.flush()
    _write_items(db, ctx, plan, data)
    ctx.audit(
        db,
        action,
        "dental_plan",
        plan.id,
        branch_id=plan.branch_id,
        details={"patient_id": str(plan.patient_id), "items": len(data.items)},
    )
    return plan


def _require_status(plan: TreatmentPlan, *allowed: str) -> None:
    if plan.status not in allowed:
        raise Conflict(f"This plan is {plan.status}.", code="invalid_transition")


def propose(db: Session, ctx: TenantContext, plan: TreatmentPlan, valid_days: int) -> None:
    clinical.require_in_branch(ctx, "clinical.write", plan.branch_id)
    _require_status(plan, "draft")
    now = datetime.now(UTC)
    plan.status, plan.proposed_at = "proposed", now
    plan.quote_valid_until = (now + timedelta(days=valid_days)).date()
    ctx.audit(
        db,
        "dental_plan.proposed",
        "dental_plan",
        plan.id,
        branch_id=plan.branch_id,
        details={"patient_id": str(plan.patient_id), "total": str(_total(db, plan))},
    )


def decide(
    db: Session, ctx: TenantContext, plan: TreatmentPlan, decision: str, note: str | None
) -> None:
    clinical.require_in_branch(ctx, "clinical.write", plan.branch_id)
    _require_status(plan, "proposed")
    plan.status, plan.decided_at, plan.decision_note = decision, datetime.now(UTC), note or None
    ctx.audit(
        db,
        f"dental_plan.{decision}",
        "dental_plan",
        plan.id,
        branch_id=plan.branch_id,
        details={"patient_id": str(plan.patient_id)},
    )


def _maybe_complete(db: Session, plan: TreatmentPlan) -> None:
    if all(i.status != "planned" for i in _items(db, plan.id)):
        plan.status, plan.closed_at = "completed", datetime.now(UTC)


def _item(db: Session, plan: TreatmentPlan, item_id: uuid.UUID) -> PlanItem:
    item = db.get(PlanItem, item_id, with_for_update=True)
    if item is None or item.plan_id != plan.id:
        raise NotFound("Treatment item not found.")
    return item


def item_done(
    db: Session,
    ctx: TenantContext,
    plan: TreatmentPlan,
    item_id: uuid.UUID,
    encounter_id: uuid.UUID | None,
) -> None:
    clinical.require_in_branch(ctx, "clinical.write", plan.branch_id)
    _require_status(plan, "accepted")
    item = _item(db, plan, item_id)
    if item.status != "planned":
        raise Conflict("This item is already done or cancelled.")
    if encounter_id is not None:
        encounter = db.get(Encounter, encounter_id)
        if encounter is None or encounter.patient_id != plan.patient_id:
            raise ValidationFailed("The consultation belongs to a different patient.")
    item.status, item.done_at, item.done_encounter_id = "done", datetime.now(UTC), encounter_id
    db.flush()
    _maybe_complete(db, plan)
    ctx.audit(
        db,
        "dental_plan.item_done",
        "dental_plan",
        plan.id,
        branch_id=plan.branch_id,
        details={"item_id": str(item.id)},
    )


def item_cancel(db: Session, ctx: TenantContext, plan: TreatmentPlan, item_id: uuid.UUID) -> None:
    clinical.require_in_branch(ctx, "clinical.write", plan.branch_id)
    _require_status(plan, "accepted")
    item = _item(db, plan, item_id)
    if item.status != "planned":
        raise Conflict("This item is already done or cancelled.")
    item.status = "cancelled"
    db.flush()
    _maybe_complete(db, plan)
    ctx.audit(
        db,
        "dental_plan.item_cancelled",
        "dental_plan",
        plan.id,
        branch_id=plan.branch_id,
        details={"item_id": str(item.id)},
    )


def cancel(db: Session, ctx: TenantContext, plan: TreatmentPlan, reason: str) -> None:
    clinical.require_in_branch(ctx, "clinical.write", plan.branch_id)
    _require_status(plan, "draft", "proposed", "accepted")
    if any(i.status == "done" for i in _items(db, plan.id)):
        raise Conflict(
            "Treatment has been done on this plan; cancel the remaining items instead.",
            code="has_done_items",
        )
    plan.status, plan.closed_at, plan.cancel_reason = "cancelled", datetime.now(UTC), reason
    ctx.audit(
        db,
        "dental_plan.cancelled",
        "dental_plan",
        plan.id,
        branch_id=plan.branch_id,
        details={"patient_id": str(plan.patient_id)},
    )


def invoice_done(db: Session, ctx: TenantContext, plan: TreatmentPlan) -> tuple[uuid.UUID, int]:
    """Put completed, not-yet-invoiced treatment on a new draft invoice (billing service)."""
    items = [i for i in _items(db, plan.id) if i.status == "done" and i.invoice_id is None]
    if not items:
        raise Conflict("There is no completed treatment to invoice.", code="nothing_to_invoice")
    for i in items:
        db.refresh(i, with_for_update=True)
    lines = []
    for i in items:
        label = i.procedure + (
            f" — tooth {i.tooth}{' ' + i.surfaces if i.surfaces else ''}" if i.tooth else ""
        )
        service = db.get(Service, i.service_id) if i.service_id else None
        if service is not None and service.is_active:
            lines.append(
                ItemInput(service_id=service.id, description=label[:300], unit_price=i.fee)
            )
        else:  # not on the price list (any more): bill the quoted line as written
            lines.append(ItemInput(description=label[:300], unit_price=i.fee))
    invoice = billing.create_invoice(
        db,
        ctx,
        InvoiceCreate(
            patient_id=plan.patient_id,
            branch_id=plan.branch_id,
            items=lines,
            notes=f"Treatment plan {plan.plan_number}",
        ),
    )
    for i in items:
        i.invoice_id = invoice.id
    db.flush()
    ctx.audit(
        db,
        "dental_plan.invoiced",
        "dental_plan",
        plan.id,
        branch_id=plan.branch_id,
        details={"invoice_id": str(invoice.id), "items": len(items)},
    )
    return invoice.id, len(items)


def _total(db: Session, plan: TreatmentPlan) -> Decimal:
    return sum((i.fee for i in _items(db, plan.id) if i.status != "cancelled"), ZERO)


def plan_reads(db: Session, rows: list[TreatmentPlan]) -> list[PlanRead]:
    names = clinical.user_names(db, {p.created_by for p in rows})
    out = []
    for p in rows:
        items = _items(db, p.id)
        live = [i for i in items if i.status != "cancelled"]
        done = [i for i in items if i.status == "done"]
        out.append(
            PlanRead(
                id=p.id,
                plan_number=p.plan_number,
                patient_id=p.patient_id,
                branch_id=p.branch_id,
                title=p.title,
                notes=p.notes,
                status=p.status,  # type: ignore[arg-type]
                created_by_name=names.get(p.created_by, ""),
                created_at=p.created_at,
                proposed_at=p.proposed_at,
                quote_valid_until=p.quote_valid_until,
                decided_at=p.decided_at,
                decision_note=p.decision_note,
                closed_at=p.closed_at,
                cancel_reason=p.cancel_reason,
                total=sum((i.fee for i in live), ZERO),
                done_total=sum((i.fee for i in done), ZERO),
                uninvoiced_done_total=sum((i.fee for i in done if i.invoice_id is None), ZERO),
                items=[PlanItemRead.model_validate(i) for i in items],
            )
        )
    return out
