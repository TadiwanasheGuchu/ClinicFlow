"""Laboratory orders and results.

Permissions (lab.read and lab.process are credential-gated like clinical permissions):
  clinical.write   request tests from an open consultation; cancel an order
  lab.read         view orders and results (every view is audited)
  lab.process      record collection, dispatch, progress and results; cancel an order
  clinical.sign    review completed results (with lab.read)
  lab.configure    maintain the test list and the laboratories directory

Status flow:  requested -> collected -> sent -> processing -> completed -> reviewed
Collection or dispatch can be skipped (a patient may go to the laboratory's own depot),
and an order can be cancelled until results exist. A new or corrected result on a
reviewed order sends it back to "completed" so a clinician reviews it again.

Audit entries carry identifiers and counts only — never test names or values, which are
clinical information and the audit log is readable without clinical access.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, NotFound, ValidationFailed
from app.core.tenancy import TenantContext, deny
from app.modules.clinical import service as clinical
from app.modules.clinical.models import Encounter
from app.modules.laboratory.models import (
    Laboratory,
    LabOrder,
    LabOrderEvent,
    LabOrderItem,
    LabResult,
    LabTest,
)
from app.modules.laboratory.schemas import (
    LabOrderCreate,
    LabOrderDetail,
    LabOrderSummary,
    OrderEventRead,
    OrderItemRead,
    ProgressChange,
    ResultBatch,
    ResultRead,
)
from app.modules.patients.models import Patient
from app.shared.counters import format_number, next_value

TRANSITIONS: dict[str, frozenset[str]] = {
    "requested": frozenset({"collected", "sent", "processing", "cancelled"}),
    "collected": frozenset({"sent", "processing", "completed", "cancelled"}),
    "sent": frozenset({"processing", "completed", "cancelled"}),
    "processing": frozenset({"completed", "cancelled"}),
    "completed": frozenset({"reviewed"}),
    "reviewed": frozenset({"completed"}),  # only when a result is added or corrected
    "cancelled": frozenset(),
}
# Results can be recorded once a specimen exists (point-of-care tests are entered after
# collection; external results once the specimen has been sent).
RESULTABLE = frozenset({"collected", "sent", "processing", "completed", "reviewed"})
STATUS_GROUPS: dict[str, tuple[str, ...]] = {
    "outstanding": ("requested", "collected", "sent", "processing"),
    "to_review": ("completed",),
    "reviewed": ("reviewed",),
    "cancelled": ("cancelled",),
}
ABNORMAL_FLAGS = ("low", "high", "critical_low", "critical_high", "abnormal")


def require_in_branch(ctx: TenantContext, permission: str, branch_id: uuid.UUID) -> None:
    if not ctx.has_in_branch(permission, branch_id):
        raise deny(ctx, permission, "laboratory_order")


def get_order(
    db: Session, ctx: TenantContext, order_id: uuid.UUID, *, lock: bool = False
) -> LabOrder:
    order = db.get(LabOrder, order_id, with_for_update=lock or None)
    if order is None:
        raise NotFound("Laboratory order not found.")
    require_in_branch(ctx, "lab.read", order.branch_id)
    return order


def _event(
    db: Session, ctx: TenantContext, order: LabOrder, to: str, note: str | None = None
) -> None:
    db.add(
        LabOrderEvent(
            organisation_id=ctx.organisation_id,
            order_id=order.id,
            from_status=None if to == "requested" else order.status,
            to_status=to,
            actor_user_id=ctx.user_id,
            occurred_at=datetime.now(UTC),
            note=note,
        )
    )


def _audit(
    db: Session, ctx: TenantContext, action: str, order: LabOrder, **details: object
) -> None:
    ctx.audit(
        db,
        action,
        "laboratory_order",
        order.id,
        branch_id=order.branch_id,
        details={"patient_id": str(order.patient_id), "number": order.order_number, **details},
    )


def _active_laboratory(db: Session, laboratory_id: uuid.UUID | None) -> None:
    if laboratory_id is None:
        return
    lab = db.get(Laboratory, laboratory_id)
    if lab is None or not lab.is_active:
        raise ValidationFailed("Choose an active laboratory.")


# --- Ordering ----------------------------------------------------------------------------


def create_order(
    db: Session, ctx: TenantContext, encounter: Encounter, data: LabOrderCreate
) -> LabOrder:
    clinical.open_for_writing(ctx, encounter)
    _active_laboratory(db, data.laboratory_id)
    items: list[LabOrderItem] = []
    for position, entry in enumerate(data.items, start=1):
        if entry.test_id is not None:
            test = db.get(LabTest, entry.test_id)
            if test is None or not test.is_active:
                raise ValidationFailed("One of the chosen tests is not on the active test list.")
            code, name, specimen = test.code, test.name, entry.specimen_type or test.specimen_type
        else:
            code, name, specimen = None, entry.test_name or "", entry.specimen_type
        items.append(
            LabOrderItem(
                organisation_id=ctx.organisation_id,
                position=position,
                test_id=entry.test_id,
                test_code=code,
                test_name=name,
                specimen_type=specimen,
            )
        )
    order = LabOrder(
        organisation_id=ctx.organisation_id,
        branch_id=encounter.branch_id,
        patient_id=encounter.patient_id,
        encounter_id=encounter.id,
        order_number=format_number("LAB", next_value(db, ctx.organisation_id, "lab_order")),
        requested_by=ctx.user_id,
        requested_at=datetime.now(UTC),
        laboratory_id=data.laboratory_id,
        urgency=data.urgency,
        clinical_information=data.clinical_information or None,
        status="requested",
    )
    db.add(order)
    db.flush()
    for item in items:
        item.order_id = order.id
    db.add_all(items)
    _event(db, ctx, order, "requested")
    db.flush()
    _audit(db, ctx, "lab_order.created", order, tests=len(items), urgency=data.urgency)
    return order


# --- Progress ----------------------------------------------------------------------------


def _final_results(db: Session, order_id: uuid.UUID) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(LabResult)
            .where(LabResult.order_id == order_id, LabResult.status == "final")
        )
        or 0
    )


def _move(db: Session, ctx: TenantContext, order: LabOrder, to: str, note: str | None) -> None:
    if to not in TRANSITIONS[order.status]:
        raise Conflict(
            f"An order that is {order.status} cannot be marked {to}.",
            code="invalid_transition",
        )
    previous = order.status
    _event(db, ctx, order, to, note)
    order.status = to
    _audit(db, ctx, "lab_order.status_changed", order, **{"from": previous, "to": to})


def progress(db: Session, ctx: TenantContext, order: LabOrder, change: ProgressChange) -> None:
    require_in_branch(ctx, "lab.process", order.branch_id)
    if change.status == "completed" and _final_results(db, order.id) == 0:
        raise Conflict("Record at least one result before completing.", code="no_results")
    _move(db, ctx, order, change.status, change.note)
    now = datetime.now(UTC)
    if change.status == "collected":
        order.collected_at, order.collected_by = now, ctx.user_id
    elif change.status == "sent":
        order.sent_at = now
    elif change.status == "completed":
        order.completed_at = now
    if change.external_reference:
        order.external_reference = change.external_reference
    if change.laboratory_id is not None:
        _active_laboratory(db, change.laboratory_id)
        order.laboratory_id = change.laboratory_id


def cancel(db: Session, ctx: TenantContext, order: LabOrder, reason: str) -> None:
    if not (
        ctx.has_in_branch("lab.process", order.branch_id)
        or ctx.has_in_branch("clinical.write", order.branch_id)
    ):
        raise deny(ctx, "lab.process", "laboratory_order")
    if _final_results(db, order.id):
        raise Conflict(
            "Results have been recorded for this order; complete it instead of cancelling.",
            code="has_results",
        )
    _move(db, ctx, order, "cancelled", reason)
    order.cancelled_at, order.cancel_reason = datetime.now(UTC), reason


def _reopen_for_review(db: Session, ctx: TenantContext, order: LabOrder, why: str) -> None:
    """A reviewed order whose results change goes back to the review list."""
    if order.status == "reviewed":
        _move(db, ctx, order, "completed", why)
        order.reviewed_at = order.reviewed_by = order.review_comment = None


def record_results(db: Session, ctx: TenantContext, order: LabOrder, batch: ResultBatch) -> None:
    require_in_branch(ctx, "lab.process", order.branch_id)
    if order.status not in RESULTABLE:
        raise Conflict(
            "Results can be recorded once the specimen has been collected or sent.",
            code="not_resultable",
        )
    items = {
        i.id: i for i in db.scalars(select(LabOrderItem).where(LabOrderItem.order_id == order.id))
    }
    now = datetime.now(UTC)
    for entry in batch.results:
        item = items.get(entry.item_id)
        if item is None:
            raise ValidationFailed("A result refers to a test that is not on this order.")
        db.add(
            LabResult(
                organisation_id=ctx.organisation_id,
                order_id=order.id,
                item_id=item.id,
                analyte=entry.analyte or item.test_name,
                value=entry.value,
                unit=entry.unit or None,
                reference_range=entry.reference_range or None,
                flag=entry.flag,
                comment=entry.comment or None,
                status="final",
                recorded_by=ctx.user_id,
                recorded_at=now,
            )
        )
    _reopen_for_review(db, ctx, order, "New result recorded")
    db.flush()
    _audit(db, ctx, "lab_result.recorded", order, results=len(batch.results))


def result_entered_in_error(
    db: Session, ctx: TenantContext, result: LabResult, order: LabOrder, reason: str
) -> None:
    require_in_branch(ctx, "lab.process", order.branch_id)
    if result.status != "final":
        raise Conflict("This result is already marked as entered in error.")
    result.status, result.status_reason = "entered_in_error", reason
    _reopen_for_review(db, ctx, order, "Result marked as entered in error")
    db.flush()
    _audit(db, ctx, "lab_result.entered_in_error", order, result_id=str(result.id))


def review(db: Session, ctx: TenantContext, order: LabOrder, comment: str | None) -> None:
    require_in_branch(ctx, "clinical.sign", order.branch_id)
    _move(db, ctx, order, "reviewed", None)
    order.reviewed_at, order.reviewed_by = datetime.now(UTC), ctx.user_id
    order.review_comment = comment or None


# --- Reading -----------------------------------------------------------------------------


def summaries(db: Session, rows: list[LabOrder]) -> list[LabOrderSummary]:
    if not rows:
        return []
    ids = [o.id for o in rows]
    patients = {
        p.id: p
        for p in db.scalars(select(Patient).where(Patient.id.in_({o.patient_id for o in rows})))
    }
    names = clinical.user_names(db, {o.requested_by for o in rows})
    labs = dict(
        db.execute(
            select(Laboratory.id, Laboratory.name).where(
                Laboratory.id.in_({o.laboratory_id for o in rows if o.laboratory_id})
            )
        ).all()
    )
    tests: dict[uuid.UUID, list[str]] = {}
    for order_id, name in db.execute(
        select(LabOrderItem.order_id, LabOrderItem.test_name)
        .where(LabOrderItem.order_id.in_(ids))
        .order_by(LabOrderItem.position)
    ):
        tests.setdefault(order_id, []).append(name)
    abnormal = dict(
        db.execute(
            select(LabResult.order_id, func.count())
            .where(
                LabResult.order_id.in_(ids),
                LabResult.status == "final",
                LabResult.flag.in_(ABNORMAL_FLAGS),
            )
            .group_by(LabResult.order_id)
        ).all()
    )
    out = []
    for o in rows:
        patient = patients[o.patient_id]
        out.append(
            LabOrderSummary(
                id=o.id,
                order_number=o.order_number,
                patient_id=o.patient_id,
                patient_name=f"{patient.first_name} {patient.last_name}",
                patient_number=patient.patient_number,
                branch_id=o.branch_id,
                encounter_id=o.encounter_id,
                status=o.status,  # type: ignore[arg-type]
                urgency=o.urgency,  # type: ignore[arg-type]
                requested_at=o.requested_at,
                requested_by=o.requested_by,
                requested_by_name=names.get(o.requested_by, ""),
                laboratory_name=labs.get(o.laboratory_id) if o.laboratory_id else None,
                tests=tests.get(o.id, []),
                abnormal_results=abnormal.get(o.id, 0),
            )
        )
    return out


def detail(db: Session, order: LabOrder) -> LabOrderDetail:
    summary = summaries(db, [order])[0]
    items = list(
        db.scalars(
            select(LabOrderItem)
            .where(LabOrderItem.order_id == order.id)
            .order_by(LabOrderItem.position)
        )
    )
    results = list(
        db.scalars(
            select(LabResult)
            .where(LabResult.order_id == order.id)
            .order_by(LabResult.recorded_at, LabResult.id)
        )
    )
    events = list(
        db.scalars(
            select(LabOrderEvent)
            .where(LabOrderEvent.order_id == order.id)
            .order_by(LabOrderEvent.occurred_at)
        )
    )
    names = clinical.user_names(
        db,
        {r.recorded_by for r in results}
        | {e.actor_user_id for e in events}
        | ({order.reviewed_by} if order.reviewed_by else set()),
    )
    by_item: dict[uuid.UUID, list[ResultRead]] = {}
    for r in results:
        by_item.setdefault(r.item_id, []).append(
            ResultRead.model_validate(
                {
                    **{
                        k: getattr(r, k) for k in ResultRead.model_fields if k != "recorded_by_name"
                    },
                    "recorded_by_name": names.get(r.recorded_by, ""),
                }
            )
        )
    return LabOrderDetail(
        **summary.model_dump(),
        clinical_information=order.clinical_information,
        laboratory_id=order.laboratory_id,
        external_reference=order.external_reference,
        collected_at=order.collected_at,
        sent_at=order.sent_at,
        completed_at=order.completed_at,
        reviewed_at=order.reviewed_at,
        reviewed_by_name=names.get(order.reviewed_by) if order.reviewed_by else None,
        review_comment=order.review_comment,
        cancelled_at=order.cancelled_at,
        cancel_reason=order.cancel_reason,
        items=[
            OrderItemRead(
                id=i.id,
                position=i.position,
                test_code=i.test_code,
                test_name=i.test_name,
                specimen_type=i.specimen_type,
                resulted=any(r.status == "final" for r in by_item.get(i.id, [])),
                results=by_item.get(i.id, []),
            )
            for i in items
        ],
        events=[
            OrderEventRead(
                from_status=e.from_status,
                to_status=e.to_status,
                actor_name=names.get(e.actor_user_id, ""),
                occurred_at=e.occurred_at,
                note=e.note,
            )
            for e in events
        ],
    )
