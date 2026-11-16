import uuid
from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field, field_validator

from app.shared.schemas import Schema


class RoleAssignment(Schema):
    role_id: uuid.UUID
    branch_id: uuid.UUID | None = None  # None = organisation-wide


def _unique(value: list[RoleAssignment]) -> list[RoleAssignment]:
    keys = {(a.role_id, a.branch_id) for a in value}
    if len(keys) != len(value):
        raise ValueError("Duplicate role assignment.")
    return value


class MemberInvite(Schema):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    roles: list[RoleAssignment] = Field(min_length=1, max_length=20)

    _unique = field_validator("roles")(_unique)

    @field_validator("email")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.lower()


class MemberRolesUpdate(Schema):
    roles: list[RoleAssignment] = Field(min_length=1, max_length=20)

    _unique = field_validator("roles")(_unique)


class AssignmentRead(Schema):
    role_id: uuid.UUID
    role_name: str
    branch_id: uuid.UUID | None
    branch_name: str | None


class MemberRead(Schema):
    id: uuid.UUID
    user_id: uuid.UUID
    email: str
    full_name: str
    phone: str | None
    status: Literal["invited", "active", "suspended"] | str
    roles: list[AssignmentRead]
    last_login_at: datetime | None
    created_at: datetime


class StatusChange(Schema):
    reason: str = Field(min_length=3, max_length=500)
