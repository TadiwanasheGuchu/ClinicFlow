import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import Conflict, Forbidden
from app.core.tenancy import TenantContext, require
from app.modules.members import service
from app.modules.members.models import Membership
from app.modules.members.schemas import MemberInvite, MemberRead, MemberRolesUpdate, StatusChange
from app.modules.users.models import User
from app.shared.schemas import Page, PageParams

router = APIRouter(prefix="/members", tags=["members"])
DB = Annotated[Session, Depends(get_db)]
CanRead = Annotated[TenantContext, Depends(require("members.read"))]
CanManage = Annotated[TenantContext, Depends(require("members.manage", org_wide=True))]


def _not_self(ctx: TenantContext, membership: Membership) -> None:
    if membership.id == ctx.membership.id:
        raise Forbidden("You cannot change your own access.", code="self_modification")


@router.get("", response_model=Page[MemberRead])
def list_members(
    ctx: CanRead,
    db: DB,
    page: Annotated[PageParams, Depends()],
    status_filter: Annotated[
        Literal["invited", "active", "suspended"] | None, Query(alias="status")
    ] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> object:
    query = select(Membership).join(User, User.id == Membership.user_id)
    if status_filter:
        query = query.where(Membership.status == status_filter)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(or_(User.full_name.ilike(pattern), User.email.ilike(pattern)))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    memberships = db.scalars(
        query.order_by(User.full_name).limit(page.limit).offset(page.offset)
    ).all()
    return Page(
        items=service.to_read(db, list(memberships)),
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{membership_id}", response_model=MemberRead)
def read_member(membership_id: uuid.UUID, ctx: CanRead, db: DB) -> object:
    return service.to_read(db, [service.get_membership(db, membership_id)])[0]


@router.post("", response_model=MemberRead, status_code=status.HTTP_201_CREATED)
def invite_member(data: MemberInvite, ctx: CanManage, db: DB) -> object:
    membership = service.invite(db, ctx, data.email, data.full_name, data.roles)
    ctx.audit(
        db,
        "member.invited",
        "membership",
        membership.id,
        details={
            "user_id": str(membership.user_id),
            "roles": [a.model_dump(mode="json") for a in data.roles],
        },
    )
    db.flush()
    result = service.to_read(db, [membership])[0]
    db.commit()
    return result


@router.put("/{membership_id}/roles", response_model=MemberRead)
def update_member_roles(
    membership_id: uuid.UUID, data: MemberRolesUpdate, ctx: CanManage, db: DB
) -> object:
    membership = service.get_membership(db, membership_id)
    _not_self(ctx, membership)
    changes = service.replace_assignments(db, ctx, membership, data.roles)
    ctx.audit(db, "member.roles_changed", "membership", membership.id, details=changes)
    db.flush()
    result = service.to_read(db, [membership])[0]
    db.commit()
    return result


@router.post("/{membership_id}/suspend", response_model=MemberRead)
def suspend_member(membership_id: uuid.UUID, data: StatusChange, ctx: CanManage, db: DB) -> object:
    membership = service.get_membership(db, membership_id)
    _not_self(ctx, membership)
    if membership.status == "suspended":
        raise Conflict("This member is already suspended.")
    if service.holds_owner(db, membership):
        if not ctx.is_owner:
            raise Forbidden("Only an owner can suspend an owner.", code="owner_only")
        service.ensure_another_owner(db, membership)
    previous = membership.status
    membership.status = "suspended"
    ctx.audit(
        db,
        "member.suspended",
        "membership",
        membership.id,
        details={"reason": data.reason, "previous_status": previous},
    )
    db.flush()
    result = service.to_read(db, [membership])[0]
    db.commit()
    return result


@router.post("/{membership_id}/reactivate", response_model=MemberRead)
def reactivate_member(
    membership_id: uuid.UUID, data: StatusChange, ctx: CanManage, db: DB
) -> object:
    membership = service.get_membership(db, membership_id)
    _not_self(ctx, membership)
    if membership.status != "suspended":
        raise Conflict("Only suspended members can be reactivated.")
    if service.holds_owner(db, membership) and not ctx.is_owner:
        raise Forbidden("Only an owner can reactivate an owner.", code="owner_only")
    # A reactivated member who never accepted their invitation returns to 'invited'.
    membership.status = "active" if membership.accepted_at else "invited"
    ctx.audit(
        db, "member.reactivated", "membership", membership.id, details={"reason": data.reason}
    )
    db.flush()
    result = service.to_read(db, [membership])[0]
    db.commit()
    return result
