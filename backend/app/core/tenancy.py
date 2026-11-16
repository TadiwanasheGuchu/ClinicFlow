"""Tenant context: which organisation a request acts in, and what the caller may do there.

Clients select the organisation with the ``X-Organisation-Id`` header. The
caller must hold an active membership of that organisation. The database
session is then scoped to the organisation so Row-Level Security applies to
every query in the request.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.config import get_settings
from app.core.db import get_db, set_scope
from app.core.exceptions import AppError, Forbidden
from app.core.permissions import OWNER_ROLE_KEY, PRIVILEGED_PERMISSIONS
from app.core.security import CurrentUser, CurrentUserDep
from app.modules.members.models import Membership, MembershipRole
from app.modules.organisations.models import Organisation
from app.modules.roles.models import Permission, Role, RolePermission


@dataclass(frozen=True)
class Grant:
    """One permission held either organisation-wide (branch_id None) or in one branch."""

    permission: str
    branch_id: uuid.UUID | None


@dataclass
class TenantContext:
    organisation: Organisation
    membership: Membership
    current: CurrentUser
    grants: frozenset[Grant]
    role_keys: frozenset[str] = field(default_factory=frozenset)

    @property
    def organisation_id(self) -> uuid.UUID:
        return self.organisation.id

    @property
    def user_id(self) -> uuid.UUID:
        return self.current.user.id

    @property
    def is_owner(self) -> bool:
        return OWNER_ROLE_KEY in self.role_keys

    @property
    def permissions(self) -> frozenset[str]:
        return frozenset(g.permission for g in self.grants)

    def has(self, permission: str) -> bool:
        """Held anywhere in the organisation (org-wide or in at least one branch)."""
        return any(g.permission == permission for g in self.grants)

    def has_org_wide(self, permission: str) -> bool:
        return Grant(permission, None) in self.grants

    def has_in_branch(self, permission: str, branch_id: uuid.UUID) -> bool:
        return self.has_org_wide(permission) or Grant(permission, branch_id) in self.grants

    def branch_scope(self, permission: str) -> set[uuid.UUID] | None:
        """None if held org-wide, otherwise the set of branches where it is held."""
        if self.has_org_wide(permission):
            return None
        return {g.branch_id for g in self.grants if g.permission == permission and g.branch_id}

    def audit(
        self,
        db: Session,
        action: str,
        resource_type: str,
        resource_id: uuid.UUID | None = None,
        *,
        branch_id: uuid.UUID | None = None,
        details: dict | None = None,
    ) -> None:
        audit.record(
            db,
            action=action,
            resource_type=resource_type,
            organisation_id=self.organisation_id,
            actor_user_id=self.user_id,
            resource_id=resource_id,
            branch_id=branch_id,
            details=details,
        )


def _parse_org_id(value: str | None) -> uuid.UUID:
    if not value:
        raise AppError("X-Organisation-Id header is required.", code="organisation_required")
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise AppError("X-Organisation-Id must be a UUID.", code="organisation_invalid") from exc


def _deny_tenant(current: CurrentUser, organisation_id: uuid.UUID, reason: str) -> Forbidden:
    audit.record_independent(
        action="access.denied",
        resource_type="organisation",
        organisation_id=organisation_id,
        actor_user_id=current.id,
        resource_id=organisation_id,
        details={"reason": reason},
    )
    # Same message whether the organisation exists or not: no tenant enumeration.
    return Forbidden("You do not have access to this organisation.", code="no_tenant_access")


def get_tenant(
    current: CurrentUserDep,
    db: Annotated[Session, Depends(get_db)],
    x_organisation_id: Annotated[str | None, Header()] = None,
) -> TenantContext:
    organisation_id = _parse_org_id(x_organisation_id)
    set_scope(db, organisation_id=organisation_id, user_id=current.id)

    membership = db.scalar(
        select(Membership).where(
            Membership.organisation_id == organisation_id, Membership.user_id == current.id
        )
    )
    if membership is None or membership.status != "active":
        raise _deny_tenant(current, organisation_id, "no_active_membership")

    organisation = db.get(Organisation, organisation_id)
    if organisation is None:
        raise _deny_tenant(current, organisation_id, "organisation_missing")
    if organisation.status != "active":
        raise Forbidden("This organisation is suspended.", code="organisation_suspended")

    rows = db.execute(
        select(Permission.code, MembershipRole.branch_id, Role.template_key)
        .join(Role, Role.id == MembershipRole.role_id)
        .join(RolePermission, RolePermission.role_id == Role.id, isouter=True)
        .join(Permission, Permission.id == RolePermission.permission_id, isouter=True)
        .where(MembershipRole.membership_id == membership.id)
    ).all()
    grants = frozenset(Grant(code, branch_id) for code, branch_id, _ in rows if code)
    role_keys = frozenset(key for _, branch_id, key in rows if key and branch_id is None)

    return TenantContext(
        organisation=organisation,
        membership=membership,
        current=current,
        grants=grants,
        role_keys=role_keys,
    )


TenantDep = Annotated[TenantContext, Depends(get_tenant)]


def _check_mfa(ctx: TenantContext, permission: str) -> None:
    acr_values = get_settings().oidc_mfa_acr_values
    if (
        acr_values
        and permission in PRIVILEGED_PERMISSIONS
        and ctx.current.claims.acr not in acr_values
    ):
        raise Forbidden(
            "Multi-factor authentication is required for this action.", code="mfa_required"
        )


def deny(ctx: TenantContext, permission: str, resource_type: str = "permission") -> Forbidden:
    audit.record_independent(
        action="access.denied",
        resource_type=resource_type,
        organisation_id=ctx.organisation_id,
        actor_user_id=ctx.user_id,
        details={"permission": permission},
    )
    return Forbidden("You do not have permission to perform this action.")


def require(permission: str, *, org_wide: bool = False) -> Callable[..., TenantContext]:
    """Dependency: the caller must hold ``permission`` (anywhere, or org-wide if requested).

    Branch-level checks for a specific resource are done in the handler with
    ``ctx.has_in_branch`` once the resource's branch is known.
    """

    def dependency(ctx: TenantDep) -> TenantContext:
        allowed = ctx.has_org_wide(permission) if org_wide else ctx.has(permission)
        if not allowed:
            raise deny(ctx, permission)
        _check_mfa(ctx, permission)
        return ctx

    return dependency
