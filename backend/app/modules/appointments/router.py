import uuid
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import ValidationFailed
from app.core.tenancy import TenantContext, require
from app.modules.appointments import service
from app.modules.appointments.models import Appointment, AppointmentEvent
from app.modules.appointments.schemas import (
    AppointmentCreate,
    AppointmentDetail,
    AppointmentEventRead,
    AppointmentRead,
    Cancel,
    Reschedule,
    Status,
    StatusChange,
)
from app.shared.schemas import Page, PageParams

router = APIRouter(prefix="/appointments", tags=["appointments"])
DB = Annotated[Session, Depends(get_db)]
CanRead = Annotated[TenantContext, Depends(require("appointments.read"))]
CanManage = Annotated[TenantContext, Depends(require("appointments.manage"))]

MAX_RANGE = timedelta(days=62)


def _detail(db: Session, appointment: Appointment) -> AppointmentDetail:
    events = db.scalars(
        select(AppointmentEvent)
        .where(AppointmentEvent.appointment_id == appointment.id)
        .order_by(AppointmentEvent.created_at)
    ).all()
    read = service.to_reads(db, [appointment])[0]
    return AppointmentDetail(
        **read.model_dump(),
        events=[AppointmentEventRead.model_validate(e) for e in events],
    )


@router.get("", response_model=Page[AppointmentRead])
def list_appointments(
    ctx: CanRead,
    db: DB,
    page: Annotated[PageParams, Depends()],
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
    branch_id: uuid.UUID | None = None,
    provider_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
    statuses: Annotated[list[Status] | None, Query(alias="status")] = None,
) -> object:
    """Calendar and list view. A date range is required unless filtering by patient."""
    if patient_id is None:
        if start is None or end is None:
            raise ValidationFailed("Provide 'from' and 'to', or a patient_id.")
        if end <= start or end - start > MAX_RANGE:
            raise ValidationFailed("The range must be positive and at most 62 days.")
    query = select(Appointment)
    if start:
        query = query.where(Appointment.end_at > start)
    if end:
        query = query.where(Appointment.start_at < end)
    for column, value in (
        (Appointment.branch_id, branch_id),
        (Appointment.provider_id, provider_id),
        (Appointment.patient_id, patient_id),
    ):
        if value:
            query = query.where(column == value)
    if statuses:
        query = query.where(Appointment.status.in_(statuses))
    # Branch-scoped readers only see their branches.
    scope = ctx.branch_scope("appointments.read")
    if scope is not None:
        query = query.where(Appointment.branch_id.in_(scope))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(Appointment.start_at, Appointment.reference)
        .limit(page.limit)
        .offset(page.offset)
    ).all()
    return Page(
        items=service.to_reads(db, list(rows)), total=total, limit=page.limit, offset=page.offset
    )


@router.post("", response_model=AppointmentDetail, status_code=status.HTTP_201_CREATED)
def book(data: AppointmentCreate, ctx: CanManage, db: DB) -> object:
    appointment = service.create(db, ctx, data)
    db.commit()
    return _detail(db, appointment)


@router.get("/{appointment_id}", response_model=AppointmentDetail)
def read_appointment(appointment_id: uuid.UUID, ctx: CanRead, db: DB) -> object:
    appointment = service.get_appointment(db, appointment_id)
    service.require_branch_permission(ctx, "appointments.read", appointment.branch_id)
    return _detail(db, appointment)


@router.post("/{appointment_id}/reschedule", response_model=AppointmentDetail)
def reschedule(appointment_id: uuid.UUID, data: Reschedule, ctx: CanManage, db: DB) -> object:
    appointment = service.get_appointment(db, appointment_id)
    service.reschedule(db, ctx, appointment, data)
    db.commit()
    return _detail(db, appointment)


@router.post("/{appointment_id}/cancel", response_model=AppointmentDetail)
def cancel(appointment_id: uuid.UUID, data: Cancel, ctx: CanManage, db: DB) -> object:
    appointment = service.get_appointment(db, appointment_id)
    service.cancel(db, ctx, appointment, data.reason)
    db.commit()
    return _detail(db, appointment)


@router.post("/{appointment_id}/status", response_model=AppointmentDetail)
def change_status(appointment_id: uuid.UUID, data: StatusChange, ctx: CanManage, db: DB) -> object:
    appointment = service.get_appointment(db, appointment_id)
    service.change_status(db, ctx, appointment, data.status, data.reason)
    db.commit()
    return _detail(db, appointment)
