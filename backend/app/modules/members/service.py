import uuid
from collections import defaultdict

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, NotFound, ValidationFailed
from app.core.permissions import OWNER_ROLE_KEY
from app.core.tenancy import TenantContext
from app.modules.branches.models import Branch
from app.modules.members.models import Membership, MembershipRole
from app.modules.members.schemas import AssignmentRead, MemberRead, RoleAssignment
from app.modules.roles.models import Role
from app.modules.roles.service import ensure_can_grant, permissions_by_role
from app.modules.users.models import User


def get_membership(db: Session, membership_id: uuid.UUID) -> Membership:
    membership = db.get(Membership, membership_id)
    if membership is None:
        raise NotFound("Member not found.")
    return membership


def to_read(db: Session, memberships: list[Membership]) -> list[MemberRead]:
    if not memberships:
        return []
    users = {
        u.id: u
        for u in db.scalars(select(User).where(User.id.in_([m.user_id for m in memberships])))
    }
    rows = db.execute(
        select(MembershipRole.membership_id, Role.id, Role.name, Branch.id, Branch.name)
        .join(Role, Role.id == MembershipRole.role_id)
        .join(Branch, Branch.id == MembershipRole.branch_id, isouter=True)
        .where(MembershipRole.membership_id.in_([m.id for m in memberships]))
        .order_by(Role.name)
    ).all()
    assignments: dict[uuid.UUID, list[AssignmentRead]] = defaultdict(list)
    for membership_id, role_id, role_name, branch_id, branch_name in rows:
        assignments[membership_id].append(
            AssignmentRead(
                role_id=role_id, role_name=role_name, branch_id=branch_id, branch_name=branch_name
            )
        )
    return [
        MemberRead(
            id=m.id,
            user_id=m.user_id,
            email=users[m.user_id].email,
            full_name=users[m.user_id].full_name,
            phone=users[m.user_id].phone,
            status=m.status,
            roles=assignments.get(m.id, []),
            last_login_at=users[m.user_id].last_login_at,
            created_at=m.created_at,
        )
        for m in memberships
    ]


def _current_assignments(db: Session, membership_id: uuid.UUID) -> list[MembershipRole]:
    return list(
        db.scalars(select(MembershipRole).where(MembershipRole.membership_id == membership_id))
    )


def _check_grantable(
    db: Session, ctx: TenantContext, assignments: list[tuple[uuid.UUID, uuid.UUID | None]]
) -> dict[uuid.UUID, Role]:
    role_ids = list({role_id for role_id, _ in assignments})
    roles = {r.id: r for r in db.scalars(select(Role).where(Role.id.in_(role_ids)))}
    if len(roles) != len(role_ids):
        raise ValidationFailed("One or more roles do not exist.")

    branch_ids = {b for _, b in assignments if b is not None}
    if branch_ids:
        active = set(
            db.scalars(
                select(Branch.id).where(Branch.id.in_(branch_ids), Branch.is_active.is_(True))
            )
        )
        if active != branch_ids:
            raise ValidationFailed("One or more branches do not exist or are inactive.")

    perms = permissions_by_role(db, role_ids)
    for role_id, branch_id in assignments:
        role = roles[role_id]
        if role.template_key == OWNER_ROLE_KEY and branch_id is not None:
            raise ValidationFailed("The Owner role is always organisation-wide.")
        ensure_can_grant(ctx, perms.get(role_id, set()), branch_id=branch_id, role=role)
    return roles


def replace_assignments(
    db: Session, ctx: TenantContext, membership: Membership, wanted: list[RoleAssignment]
) -> dict[str, list[dict[str, str | None]]]:
    existing = _current_assignments(db, membership.id)
    current_keys = {(a.role_id, a.branch_id) for a in existing}
    wanted_keys = {(a.role_id, a.branch_id) for a in wanted}
    added = wanted_keys - current_keys
    removed = current_keys - wanted_keys

    # The caller must be able to grant both what is added and what is removed.
    _check_grantable(db, ctx, list(added | removed))

    if any(_is_owner_role(db, role_id) for role_id, _ in removed):
        ensure_another_owner(db, membership)

    if removed:
        db.execute(
            delete(MembershipRole).where(
                MembershipRole.id.in_(
                    [a.id for a in existing if (a.role_id, a.branch_id) in removed]
                )
            )
        )
    db.add_all(
        MembershipRole(
            organisation_id=membership.organisation_id,
            membership_id=membership.id,
            role_id=role_id,
            branch_id=branch_id,
        )
        for role_id, branch_id in added
    )

    def fmt(keys: set[tuple[uuid.UUID, uuid.UUID | None]]) -> list[dict[str, str | None]]:
        return [
            {"role_id": str(r), "branch_id": str(b) if b else None}
            for r, b in sorted(keys, key=str)
        ]

    return {"added": fmt(added), "removed": fmt(removed)}


def _is_owner_role(db: Session, role_id: uuid.UUID) -> bool:
    role = db.get(Role, role_id)
    return role is not None and role.template_key == OWNER_ROLE_KEY


def holds_owner(db: Session, membership: Membership) -> bool:
    return bool(
        db.scalar(
            select(func.count())
            .select_from(MembershipRole)
            .join(Role, Role.id == MembershipRole.role_id)
            .where(
                MembershipRole.membership_id == membership.id,
                Role.template_key == OWNER_ROLE_KEY,
            )
        )
    )


def ensure_another_owner(db: Session, membership: Membership) -> None:
    """An organisation must always keep at least one active owner."""
    others = db.scalar(
        select(func.count())
        .select_from(MembershipRole)
        .join(Role, Role.id == MembershipRole.role_id)
        .join(Membership, Membership.id == MembershipRole.membership_id)
        .where(
            Role.template_key == OWNER_ROLE_KEY,
            Membership.status == "active",
            Membership.id != membership.id,
        )
    )
    if not others:
        raise Conflict("The organisation must keep at least one active owner.", code="last_owner")


def invite(
    db: Session, ctx: TenantContext, email: str, full_name: str, roles: list[RoleAssignment]
) -> Membership:
    _check_grantable(db, ctx, [(a.role_id, a.branch_id) for a in roles])

    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None:
        user = User(email=email, full_name=full_name, status="active", is_platform_admin=False)
        db.add(user)
        db.flush()
    elif (
        db.scalar(
            select(Membership).where(
                Membership.organisation_id == ctx.organisation_id, Membership.user_id == user.id
            )
        )
        is not None
    ):
        raise Conflict("This person is already a member of the organisation.")

    membership = Membership(
        organisation_id=ctx.organisation_id,
        user_id=user.id,
        status="invited",
        invited_by=ctx.user_id,
    )
    db.add(membership)
    db.flush()
    db.add_all(
        MembershipRole(
            organisation_id=ctx.organisation_id,
            membership_id=membership.id,
            role_id=a.role_id,
            branch_id=a.branch_id,
        )
        for a in roles
    )
    return membership
