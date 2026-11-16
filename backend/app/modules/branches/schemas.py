import re
import uuid
from datetime import datetime
from itertools import pairwise

from pydantic import EmailStr, Field, field_validator, model_validator

from app.shared.schemas import Schema

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class TimeInterval(Schema):
    open: str
    close: str

    @model_validator(mode="after")
    def _valid(self) -> "TimeInterval":
        if not (_TIME.match(self.open) and _TIME.match(self.close)):
            raise ValueError("Times must be HH:MM (24-hour).")
        if self.open >= self.close:
            raise ValueError("Opening time must be before closing time.")
        return self


OperatingHours = dict[str, list[TimeInterval]]


def _check_hours(value: OperatingHours | None) -> OperatingHours | None:
    if value is None:
        return value
    for day, intervals in value.items():
        if day not in WEEKDAYS:
            raise ValueError(f"Unknown weekday '{day}'. Use {', '.join(WEEKDAYS)}.")
        ordered = sorted(intervals, key=lambda i: i.open)
        for earlier, later in pairwise(ordered):
            if later.open < earlier.close:
                raise ValueError(f"Overlapping opening hours on {day}.")
    return value


class _BranchFields(Schema):
    address: str | None = Field(None, max_length=1000)
    phone: str | None = Field(None, max_length=32, pattern=r"^\+?[0-9 ()-]{6,32}$")
    email: EmailStr | None = None


class BranchCreate(_BranchFields):
    name: str = Field(min_length=2, max_length=200)
    branch_code: str = Field(pattern=r"^[A-Z0-9-]{2,20}$")
    operating_hours: OperatingHours = Field(default_factory=dict)

    _hours = field_validator("operating_hours")(_check_hours)


class BranchUpdate(_BranchFields):
    name: str | None = Field(None, min_length=2, max_length=200)
    operating_hours: OperatingHours | None = None
    is_active: bool | None = None

    _hours = field_validator("operating_hours")(_check_hours)

    @model_validator(mode="after")
    def _required_not_null(self) -> "BranchUpdate":
        for name in ("name", "operating_hours", "is_active"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null.")
        return self


class BranchRead(Schema):
    id: uuid.UUID
    name: str
    branch_code: str
    address: str | None
    phone: str | None
    email: str | None
    operating_hours: OperatingHours
    is_active: bool
    created_at: datetime
