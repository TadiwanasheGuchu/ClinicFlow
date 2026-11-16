import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.db import get_db, set_scope
from app.core.exceptions import Conflict, NotFound
from app.core.security import CurrentUser, CurrentUserDep
from app.core.tenancy import TenantDep
from app.modules.members.models import Membership
from app.modules.organisations.models import Organisation
from app.modules.users.schemas import AccessRead, GrantRead, MembershipSummary, MeRead, MeUpdate

router = APIRouter(prefix="/me", tags=["me"])
DB = Annotated[Session, Depends(get_db)]


def _me(db: Session, current: CurrentUser) -> MeRead:
    # RLS: without a tenant scope, only the caller's own memberships and their
    # organisations are visible.
    rows = db.execute(
        select(Membership, Organisation)
        .join(Organisation, Organisation.id == Membership.organisation_id)
        .where(Membership.user_id == current.id)
        .order_by(Organisation.name)
    ).all()
    user = current.user
    return MeRead(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        is_platform_admin=user.is_platform_admin,
        last_login_at=user.last_login_at,
        memberships=[
            MembershipSummary(
                organisation_id=org.id,
                organisation_name=org.name,
                organisation_status=org.status,
                membership_id=m.id,
                status=m.status,
            )
            for m, org in rows
        ],
    )


@router.get("", response_model=MeRead)
def read_me(current: CurrentUserDep, db: DB) -> object:
    return _me(db, current)


@router.patch("", response_model=MeRead)
def update_me(data: MeUpdate, current: CurrentUserDep, db: DB) -> object:
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(current.user, key, value)
    audit.record(
        db,
        action="user.profile_updated",
        resource_type="user",
        resource_id=current.id,
        organisation_id=None,
        actor_user_id=current.id,
        details={"fields": sorted(changes)},
    )
    db.commit()
    return _me(db, current)


@router.post("/invitations/{organisation_id}/accept", response_model=MeRead)
def accept_invitation(organisation_id: uuid.UUID, current: CurrentUserDep, db: DB) -> object:
    set_scope(db, organisation_id=organisation_id, user_id=current.id)
    membership = db.scalar(
        select(Membership).where(
            Membership.organisation_id == organisation_id, Membership.user_id == current.id
        )
    )
    if membership is None:
        raise NotFound("Invitation not found.")
    if membership.status != "invited":
        raise Conflict("There is no pending invitation for this organisation.")
    membership.status = "active"
    membership.accepted_at = datetime.now(UTC)
    audit.record(
        db,
        action="member.invitation_accepted",
        resource_type="membership",
        resource_id=membership.id,
        organisation_id=organisation_id,
        actor_user_id=current.id,
    )
    db.commit()
    set_scope(db, user_id=current.id)
    return _me(db, current)


@router.get("/access", response_model=AccessRead)
def read_access(ctx: TenantDep) -> object:
    """Effective permissions in the selected organisation (for UI gating; the API enforces)."""
    return AccessRead(
        organisation_id=ctx.organisation_id,
        membership_id=ctx.membership.id,
        is_owner=ctx.is_owner,
        permissions=sorted(ctx.permissions),
        grants=[
            GrantRead(permission=g.permission, branch_id=g.branch_id)
            for g in sorted(ctx.grants, key=lambda g: (g.permission, str(g.branch_id)))
        ],
    )
