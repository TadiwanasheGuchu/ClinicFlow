import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.tenancy import TenantContext, require
from app.modules.audit.models import AuditLog
from app.shared.schemas import Page, PageParams, Schema

router = APIRouter(prefix="/audit-logs", tags=["audit"])


class AuditLogRead(Schema):
    id: uuid.UUID
    timestamp: datetime
    actor_user_id: uuid.UUID | None
    action: str
    resource_type: str
    resource_id: uuid.UUID | None
    branch_id: uuid.UUID | None
    request_id: str | None
    source_ip: str | None
    details: dict[str, Any]


@router.get("", response_model=Page[AuditLogRead])
def list_audit_logs(
    ctx: Annotated[TenantContext, Depends(require("audit.read", org_wide=True))],
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[PageParams, Depends()],
    action: Annotated[str | None, Query(max_length=100)] = None,
    resource_type: Annotated[str | None, Query(max_length=100)] = None,
    resource_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> object:
    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if resource_id:
        query = query.where(AuditLog.resource_id == resource_id)
    if actor_user_id:
        query = query.where(AuditLog.actor_user_id == actor_user_id)
    if since:
        query = query.where(AuditLog.timestamp >= since)
    if until:
        query = query.where(AuditLog.timestamp < until)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(
        query.order_by(AuditLog.timestamp.desc(), AuditLog.id).limit(page.limit).offset(page.offset)
    ).all()
    items = [
        AuditLogRead.model_validate(
            {
                **{c: getattr(r, c) for c in AuditLogRead.model_fields if c != "source_ip"},
                "source_ip": str(r.source_ip) if r.source_ip else None,
            }
        )
        for r in rows
    ]
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)
