import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import Conflict, NotFound
from app.core.tenancy import TenantContext, require
from app.modules.notifications.models import Notification
from app.shared.schemas import Page, PageParams, Schema

router = APIRouter(prefix="/notifications", tags=["notifications"])
DB = Annotated[Session, Depends(get_db)]


class NotificationRead(Schema):
    id: uuid.UUID
    patient_id: uuid.UUID | None
    appointment_id: uuid.UUID | None
    event_type: str
    channel: str
    recipient: str | None
    body: str
    delivery_status: str
    scheduled_for: datetime
    attempts: int
    next_attempt_at: datetime | None
    last_error: str | None
    sent_at: datetime | None
    created_at: datetime


@router.get("", response_model=Page[NotificationRead])
def list_notifications(
    ctx: Annotated[TenantContext, Depends(require("appointments.read"))],
    db: DB,
    page: Annotated[PageParams, Depends()],
    appointment_id: uuid.UUID | None = None,
    patient_id: uuid.UUID | None = None,
    status: Annotated[
        Literal["pending", "sent", "failed", "cancelled", "skipped"] | None, Query()
    ] = None,
) -> object:
    query = select(Notification)
    if appointment_id:
        query = query.where(Notification.appointment_id == appointment_id)
    if patient_id:
        query = query.where(Notification.patient_id == patient_id)
    if status:
        query = query.where(Notification.delivery_status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(Notification.scheduled_for.desc()).limit(page.limit).offset(page.offset)
    ).all()
    return Page(items=rows, total=total, limit=page.limit, offset=page.offset)


@router.post("/{notification_id}/retry", response_model=NotificationRead)
def retry(
    notification_id: uuid.UUID,
    ctx: Annotated[TenantContext, Depends(require("appointments.manage"))],
    db: DB,
) -> object:
    """Queue a failed message for delivery again (e.g. after a provider outage)."""
    notification = db.get(Notification, notification_id)
    if notification is None:
        raise NotFound("Message not found.")
    if notification.delivery_status != "failed":
        raise Conflict("Only failed messages can be retried.")
    notification.delivery_status = "pending"
    notification.attempts = 0
    notification.next_attempt_at = None
    ctx.audit(
        db,
        "notification.retried",
        "notification",
        notification.id,
        details={"event_type": notification.event_type, "last_error": notification.last_error},
    )
    db.commit()
    return notification
