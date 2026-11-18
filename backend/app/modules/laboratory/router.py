import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import Conflict, NotFound
from app.core.tenancy import TenantContext, TenantDep, deny, require
from app.modules.clinical import service as clinical
from app.modules.clinical.models import Encounter
from app.modules.clinical.schemas import StatusReason
from app.modules.laboratory import service
from app.modules.laboratory.models import Laboratory, LabOrder, LabResult, LabTest
from app.modules.laboratory.schemas import (
    CancelOrder,
    LaboratoryRead,
    LaboratoryWrite,
    LabOrderCreate,
    LabOrderDetail,
    LabOrderSummary,
    LabTestRead,
    LabTestWrite,
    ProgressChange,
    ResultBatch,
    ReviewOrder,
)
from app.shared.schemas import Page, PageParams

router = APIRouter(tags=["laboratory"])
DB = Annotated[Session, Depends(get_db)]
Reader = Annotated[TenantContext, Depends(require("lab.read"))]
Processor = Annotated[TenantContext, Depends(require("lab.process"))]
Configurer = Annotated[TenantContext, Depends(require("lab.configure", org_wide=True))]


def _lists_reader(ctx: TenantDep) -> TenantContext:
    """The test list and laboratories are needed to order, process or configure."""
    if not any(ctx.has(p) for p in ("lab.read", "clinical.write", "lab.configure")):
        raise deny(ctx, "lab.read")
    return ctx


ListReader = Annotated[TenantContext, Depends(_lists_reader)]


# --- Test list and laboratories ----------------------------------------------------------


@router.get("/laboratory-tests", response_model=list[LabTestRead])
def list_tests(ctx: ListReader, db: DB, include_inactive: bool = False) -> object:
    query = select(LabTest).order_by(LabTest.category.nulls_last(), LabTest.name)
    if not include_inactive:
        query = query.where(LabTest.is_active.is_(True))
    return db.scalars(query).all()


def _save(db: Session, ctx: TenantContext, row: LabTest | Laboratory, action: str) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        what = "test with this code" if isinstance(row, LabTest) else "laboratory with this name"
        raise Conflict(f"A {what} already exists.") from exc
    ctx.audit(db, action, action.split(".")[0], row.id)
    db.commit()


@router.post("/laboratory-tests", response_model=LabTestRead, status_code=status.HTTP_201_CREATED)
def create_test(data: LabTestWrite, ctx: Configurer, db: DB) -> object:
    test = LabTest(organisation_id=ctx.organisation_id, **data.model_dump())
    db.add(test)
    _save(db, ctx, test, "laboratory_test.created")
    return test


@router.put("/laboratory-tests/{test_id}", response_model=LabTestRead)
def update_test(test_id: uuid.UUID, data: LabTestWrite, ctx: Configurer, db: DB) -> object:
    test = db.get(LabTest, test_id)
    if test is None:
        raise NotFound("Test not found.")
    for key, value in data.model_dump().items():
        setattr(test, key, value)
    _save(db, ctx, test, "laboratory_test.updated")
    return test


@router.get("/laboratories", response_model=list[LaboratoryRead])
def list_laboratories(ctx: ListReader, db: DB, include_inactive: bool = False) -> object:
    query = select(Laboratory).order_by(Laboratory.name)
    if not include_inactive:
        query = query.where(Laboratory.is_active.is_(True))
    return db.scalars(query).all()


@router.post("/laboratories", response_model=LaboratoryRead, status_code=status.HTTP_201_CREATED)
def create_laboratory(data: LaboratoryWrite, ctx: Configurer, db: DB) -> object:
    lab = Laboratory(organisation_id=ctx.organisation_id, **data.model_dump())
    db.add(lab)
    _save(db, ctx, lab, "laboratory.created")
    return lab


@router.put("/laboratories/{laboratory_id}", response_model=LaboratoryRead)
def update_laboratory(
    laboratory_id: uuid.UUID, data: LaboratoryWrite, ctx: Configurer, db: DB
) -> object:
    lab = db.get(Laboratory, laboratory_id)
    if lab is None:
        raise NotFound("Laboratory not found.")
    for key, value in data.model_dump().items():
        setattr(lab, key, value)
    _save(db, ctx, lab, "laboratory.updated")
    return lab


# --- Orders ------------------------------------------------------------------------------


@router.post(
    "/encounters/{encounter_id}/lab-orders",
    response_model=LabOrderDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_order(
    encounter_id: uuid.UUID,
    data: LabOrderCreate,
    ctx: Annotated[TenantContext, Depends(require("clinical.write"))],
    db: DB,
) -> object:
    encounter = db.get(Encounter, encounter_id)
    if encounter is None:
        raise NotFound("Consultation not found.")
    order = service.create_order(db, ctx, encounter, data)
    db.commit()
    return service.detail(db, order)


@router.get("/lab-orders", response_model=Page[LabOrderSummary])
def list_orders(
    ctx: Reader,
    db: DB,
    page: Annotated[PageParams, Depends()],
    group: Literal["outstanding", "to_review", "reviewed", "cancelled", "all"] = "outstanding",
    patient_id: uuid.UUID | None = None,
    encounter_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    mine: bool = False,
) -> object:
    query = select(LabOrder)
    scope = ctx.branch_scope("lab.read")
    if scope is not None:
        query = query.where(LabOrder.branch_id.in_(scope))
    if branch_id is not None:
        query = query.where(LabOrder.branch_id == branch_id)
    if group != "all":
        query = query.where(LabOrder.status.in_(service.STATUS_GROUPS[group]))
    if patient_id is not None:
        query = query.where(LabOrder.patient_id == patient_id)
    if encounter_id is not None:
        query = query.where(LabOrder.encounter_id == encounter_id)
    if mine:
        query = query.where(LabOrder.requested_by == ctx.user_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    # Outstanding work is oldest first (urgent at the top); history is newest first.
    order_by = (
        (LabOrder.urgency.desc(), LabOrder.requested_at)
        if group in ("outstanding", "to_review")
        else (LabOrder.requested_at.desc(),)
    )
    rows = list(db.scalars(query.order_by(*order_by).limit(page.limit).offset(page.offset)))
    if patient_id is not None:
        clinical.log_view(db, ctx, patient_id, "lab_orders")
    db.commit()
    return Page(
        items=service.summaries(db, rows), total=total, limit=page.limit, offset=page.offset
    )


@router.get("/lab-orders/{order_id}", response_model=LabOrderDetail)
def read_order(order_id: uuid.UUID, ctx: Reader, db: DB) -> object:
    order = service.get_order(db, ctx, order_id)
    clinical.log_view(db, ctx, order.patient_id, "lab_order", order.id)
    db.commit()
    return service.detail(db, order)


@router.post("/lab-orders/{order_id}/progress", response_model=LabOrderDetail)
def progress(order_id: uuid.UUID, data: ProgressChange, ctx: Processor, db: DB) -> object:
    order = service.get_order(db, ctx, order_id, lock=True)
    service.progress(db, ctx, order, data)
    db.commit()
    return service.detail(db, order)


@router.post("/lab-orders/{order_id}/cancel", response_model=LabOrderDetail)
def cancel(order_id: uuid.UUID, data: CancelOrder, ctx: TenantDep, db: DB) -> object:
    order = service.get_order(db, ctx, order_id, lock=True)
    service.cancel(db, ctx, order, data.reason)
    db.commit()
    return service.detail(db, order)


@router.post(
    "/lab-orders/{order_id}/results",
    response_model=LabOrderDetail,
    status_code=status.HTTP_201_CREATED,
)
def record_results(order_id: uuid.UUID, data: ResultBatch, ctx: Processor, db: DB) -> object:
    order = service.get_order(db, ctx, order_id, lock=True)
    service.record_results(db, ctx, order, data)
    db.commit()
    return service.detail(db, order)


@router.post("/lab-results/{result_id}/entered-in-error", response_model=LabOrderDetail)
def result_error(result_id: uuid.UUID, data: StatusReason, ctx: Processor, db: DB) -> object:
    result = db.get(LabResult, result_id)
    if result is None:
        raise NotFound("Result not found.")
    order = service.get_order(db, ctx, result.order_id, lock=True)
    service.result_entered_in_error(db, ctx, result, order, data.reason)
    db.commit()
    return service.detail(db, order)


@router.post("/lab-orders/{order_id}/review", response_model=LabOrderDetail)
def review(
    order_id: uuid.UUID,
    data: ReviewOrder,
    ctx: Annotated[TenantContext, Depends(require("clinical.sign"))],
    db: DB,
) -> object:
    order = service.get_order(db, ctx, order_id, lock=True)
    service.review(db, ctx, order, data.comment)
    db.commit()
    return service.detail(db, order)
