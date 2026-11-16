import uuid
from datetime import datetime

from pydantic import Field, model_validator

from app.shared.schemas import Schema


class MembershipSummary(Schema):
    organisation_id: uuid.UUID
    organisation_name: str
    organisation_status: str
    membership_id: uuid.UUID
    status: str


class MeRead(Schema):
    id: uuid.UUID
    email: str
    full_name: str
    phone: str | None
    is_platform_admin: bool
    last_login_at: datetime | None
    memberships: list[MembershipSummary]


class MeUpdate(Schema):
    full_name: str | None = Field(None, min_length=2, max_length=200)
    phone: str | None = Field(None, max_length=32, pattern=r"^\+?[0-9 ()-]{6,32}$")

    @model_validator(mode="after")
    def _name_not_null(self) -> "MeUpdate":
        if "full_name" in self.model_fields_set and self.full_name is None:
            raise ValueError("full_name cannot be null.")
        return self


class GrantRead(Schema):
    permission: str
    branch_id: uuid.UUID | None


class AccessRead(Schema):
    organisation_id: uuid.UUID
    membership_id: uuid.UUID
    is_owner: bool
    permissions: list[str]
    grants: list[GrantRead]
