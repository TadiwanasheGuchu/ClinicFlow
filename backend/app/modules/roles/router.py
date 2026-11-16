import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import Conflict, Forbidden, NotFound
from app.core.tenancy import TenantContext, require
from app.modules.members.models import MembershipRole
from app.modules.roles.models import Permission, Role
from app.modules.roles.schemas import PermissionRead, RoleCreate, RoleRead, RoleUpdate
from app.modules.roles.service import (
    ensure_can_grant,
    permissions_by_role,
    set_role_permissions,
    to_read,
)

router = APIRouter(tags=["roles"])
DB = Annotated[Session, Depends(get_db)]
CanRead = Annotated[TenantContext, Depends(require("roles.read"))]
CanManage = Annotated[TenantContext, Depends(require("roles.manage", org_wide=True))]


def _get_role(db: Session, role_id: uuid.UUID) -> Role:
    role = db.get(Role, role_id)
    if role is None:
        raise NotFound("Role not found.")
    return role


@router.get("/permissions", response_model=list[PermissionRead])
def list_permissions(ctx: CanRead, db: DB) -> object:
    return db.scalars(select(Permission).order_by(Permission.code)).all()


@router.get("/roles", response_model=list[RoleRead])
def list_roles(ctx: CanRead, db: DB) -> object:
    roles = db.scalars(select(Role).order_by(Role.is_system.desc(), Role.name)).all()
    return to_read(db, list(roles))


@router.get("/roles/{role_id}", response_model=RoleRead)
def read_role(role_id: uuid.UUID, ctx: CanRead, db: DB) -> object:
    return to_read(db, [_get_role(db, role_id)])[0]


@router.post("/roles", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
def create_role(data: RoleCreate, ctx: CanManage, db: DB) -> object:
    ensure_can_grant(ctx, set(data.permissions))
    role = Role(
        organisation_id=ctx.organisation_id,
        name=data.name,
        description=data.description,
        is_system=False,
    )
    db.add(role)
    try:
        db.flush()
    except IntegrityError as exc:
        raise Conflict("A role with this name already exists.") from exc
    set_role_permissions(db, role, data.permissions)
    ctx.audit(
        db,
        "role.created",
        "role",
        role.id,
        details={"name": role.name, "permissions": data.permissions},
    )
    db.flush()
    result = to_read(db, [role])[0]
    db.commit()
    return result


@router.patch("/roles/{role_id}", response_model=RoleRead)
def update_role(role_id: uuid.UUID, data: RoleUpdate, ctx: CanManage, db: DB) -> object:
    role = _get_role(db, role_id)
    if role.is_system:
        raise Forbidden("System roles cannot be modified.", code="system_role")

    details: dict[str, object] = {}
    if data.permissions is not None:
        before = permissions_by_role(db, [role.id]).get(role.id, set())
        after = set(data.permissions)
        # Changing a role changes what every holder can do: the caller must be
        # able to grant everything added and everything removed.
        ensure_can_grant(ctx, after ^ before, role=role)
        set_role_permissions(db, role, data.permissions)
        details["permissions_added"] = sorted(after - before)
        details["permissions_removed"] = sorted(before - after)
    for field in ("name", "description"):
        if field in data.model_fields_set:
            details[field] = {"before": getattr(role, field), "after": getattr(data, field)}
            setattr(role, field, getattr(data, field))
    try:
        db.flush()
    except IntegrityError as exc:
        raise Conflict("A role with this name already exists.") from exc
    ctx.audit(db, "role.updated", "role", role.id, details=details)
    db.flush()
    result = to_read(db, [role])[0]
    db.commit()
    return result


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(role_id: uuid.UUID, ctx: CanManage, db: DB) -> Response:
    role = _get_role(db, role_id)
    if role.is_system:
        raise Forbidden("System roles cannot be deleted.", code="system_role")
    if db.scalar(select(exists().where(MembershipRole.role_id == role.id))):
        raise Conflict("This role is assigned to staff. Remove the assignments first.")
    ensure_can_grant(ctx, permissions_by_role(db, [role.id]).get(role.id, set()), role=role)
    ctx.audit(db, "role.deleted", "role", role.id, details={"name": role.name})
    db.delete(role)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
