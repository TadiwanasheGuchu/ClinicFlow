import uuid
from collections import defaultdict

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import Forbidden
from app.core.permissions import OWNER_ROLE_KEY
from app.core.tenancy import TenantContext, deny
from app.modules.members.models import MembershipRole
from app.modules.roles.models import Permission, Role, RolePermission
from app.modules.roles.schemas import RoleRead


def permissions_by_role(db: Session, role_ids: list[uuid.UUID]) -> dict[uuid.UUID, set[str]]:
    result: dict[uuid.UUID, set[str]] = defaultdict(set)
    if not role_ids:
        return result
    rows = db.execute(
        select(RolePermission.role_id, Permission.code)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(RolePermission.role_id.in_(role_ids))
    ).all()
    for role_id, code in rows:
        result[role_id].add(code)
    return result


def to_read(db: Session, roles: list[Role]) -> list[RoleRead]:
    ids = [r.id for r in roles]
    perms = permissions_by_role(db, ids)
    counts = (
        dict(
            db.execute(
                select(MembershipRole.role_id, func.count())
                .where(MembershipRole.role_id.in_(ids))
                .group_by(MembershipRole.role_id)
            ).all()
        )
        if ids
        else {}
    )
    return [
        RoleRead(
            id=r.id,
            name=r.name,
            description=r.description,
            template_key=r.template_key,
            is_system=r.is_system,
            permissions=sorted(perms.get(r.id, set())),
            assignment_count=counts.get(r.id, 0),
            created_at=r.created_at,
        )
        for r in roles
    ]


def set_role_permissions(db: Session, role: Role, codes: list[str]) -> None:
    db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
    if not codes:
        return
    permission_ids = db.scalars(select(Permission.id).where(Permission.code.in_(codes))).all()
    db.add_all(
        RolePermission(role_id=role.id, permission_id=pid, organisation_id=role.organisation_id)
        for pid in permission_ids
    )


def ensure_can_grant(
    ctx: TenantContext,
    permissions: set[str],
    *,
    branch_id: uuid.UUID | None = None,
    role: Role | None = None,
) -> None:
    """Prevent privilege escalation: a caller may only grant permissions they hold themselves
    (org-wide, or in the target branch). The Owner role may only be granted by an Owner.
    Owners are the organisation's root of trust and may grant any permission."""
    if role is not None and role.template_key == OWNER_ROLE_KEY and not ctx.is_owner:
        raise Forbidden("Only an owner can grant or remove the Owner role.", code="owner_only")
    if ctx.is_owner:
        return
    for code in permissions:
        held = ctx.has_org_wide(code) if branch_id is None else ctx.has_in_branch(code, branch_id)
        if not held:
            raise deny(ctx, code, "role_grant")
