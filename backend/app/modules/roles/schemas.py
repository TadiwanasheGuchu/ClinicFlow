import uuid
from datetime import datetime

from pydantic import Field, field_validator, model_validator

from app.core.permissions import PERMISSION_CODES
from app.shared.schemas import Schema


def _check_codes(value: list[str] | None) -> list[str] | None:
    if value is None:
        return value
    unknown = sorted(set(value) - PERMISSION_CODES)
    if unknown:
        raise ValueError(f"Unknown permissions: {', '.join(unknown)}")
    return sorted(set(value))


class PermissionRead(Schema):
    code: str
    description: str
    privileged: bool


class RoleCreate(Schema):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(None, max_length=1000)
    permissions: list[str] = Field(default_factory=list)

    _codes = field_validator("permissions")(_check_codes)


class RoleUpdate(Schema):
    name: str | None = Field(None, min_length=2, max_length=100)
    description: str | None = Field(None, max_length=1000)
    permissions: list[str] | None = None

    _codes = field_validator("permissions")(_check_codes)

    @model_validator(mode="after")
    def _required_not_null(self) -> "RoleUpdate":
        for name in ("name", "permissions"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null.")
        return self


class RoleRead(Schema):
    id: uuid.UUID
    name: str
    description: str | None
    template_key: str | None
    is_system: bool
    permissions: list[str]
    assignment_count: int
    created_at: datetime
