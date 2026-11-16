"""Platform administration: tenant lifecycle only.

Platform administrators can list organisations and suspend or reactivate them.
They receive NO access to any organisation's staff, patient or clinical data;
the database scope used here only opens the ``organisations`` table.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.db import get_db, set_scope
from app.core.exceptions import Forbidden, NotFound
from app.core.security import CurrentUser, CurrentUserDep
from app.modules.organisations.models import Organisation
from app.shared.schemas import Page, PageParams, Schema

router = APIRouter(prefix="/platform", tags=["platform"])
DB = Annotated[Session, Depends(get_db)]


def platform_admin(current: CurrentUserDep, db: DB) -> CurrentUser:
    if not current.user.is_platform_admin:
        audit.record_independent(
            action="access.denied",
            resource_type="platform",
            organisation_id=None,
            actor_user_id=current.id,
        )
        raise Forbidden("Platform administrator access required.")
    set_scope(db, user_id=current.id, platform=True)
    return current


PlatformAdmin = Annotated[CurrentUser, Depends(platform_admin)]


class TenantRead(Schema):
    id: uuid.UUID
    name: str
    email: str | None
    phone: str | None
    status: str
    created_at: datetime


class TenantStatusUpdate(Schema):
    status: Literal["active", "suspended"]
    reason: str = Field(min_length=3, max_length=500)


@router.get("/organisations", response_model=Page[TenantRead])
def list_tenants(
    admin: PlatformAdmin,
    db: DB,
    page: Annotated[PageParams, Depends()],
    q: Annotated[str | None, Query(max_length=100)] = None,
    status: Literal["active", "suspended"] | None = None,
) -> object:
    query = select(Organisation)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(
            or_(Organisation.name.ilike(pattern), Organisation.email.ilike(pattern))
        )
    if status:
        query = query.where(Organisation.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(Organisation.created_at.desc()).limit(page.limit).offset(page.offset)
    ).all()
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.patch("/organisations/{organisation_id}", response_model=TenantRead)
def update_tenant_status(
    organisation_id: uuid.UUID, data: TenantStatusUpdate, admin: PlatformAdmin, db: DB
) -> object:
    organisation = db.get(Organisation, organisation_id)
    if organisation is None:
        raise NotFound("Organisation not found.")
    previous = organisation.status
    organisation.status = data.status
    # Recorded against the organisation so its own administrators can see it.
    audit.record(
        db,
        action="platform.organisation_status_changed",
        resource_type="organisation",
        resource_id=organisation.id,
        organisation_id=organisation.id,
        actor_user_id=admin.id,
        details={"from": previous, "to": data.status, "reason": data.reason},
    )
    db.commit()
    return organisation
