import uuid
from datetime import datetime
from typing import Literal
from zoneinfo import available_timezones

from pydantic import EmailStr, Field, field_validator, model_validator

from app.shared.schemas import Schema

_TIMEZONES = available_timezones()


class OrganisationSettings(Schema):
    """Typed organisation-level settings stored in ``organisations.settings``."""

    patient_number_prefix: str = Field("P", pattern=r"^[A-Z]{1,5}$")
    invoice_number_prefix: str = Field("INV", pattern=r"^[A-Z]{1,5}$")
    default_appointment_minutes: int = Field(15, ge=5, le=240)
    booking_buffer_minutes: int = Field(0, ge=0, le=120)


class OrganisationSettingsUpdate(Schema):
    patient_number_prefix: str | None = Field(None, pattern=r"^[A-Z]{1,5}$")
    invoice_number_prefix: str | None = Field(None, pattern=r"^[A-Z]{1,5}$")
    default_appointment_minutes: int | None = Field(None, ge=5, le=240)
    booking_buffer_minutes: int | None = Field(None, ge=0, le=120)


class _OrganisationFields(Schema):
    legal_name: str | None = Field(None, max_length=200)
    registration_number: str | None = Field(None, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=32, pattern=r"^\+?[0-9 ()-]{6,32}$")


def _check_timezone(value: str | None) -> str | None:
    if value is not None and value not in _TIMEZONES:
        raise ValueError("Unknown timezone.")
    return value


class OrganisationCreate(_OrganisationFields):
    name: str = Field(min_length=2, max_length=200)
    timezone: str = "Africa/Windhoek"
    first_branch_name: str = Field("Main branch", min_length=2, max_length=200)
    first_branch_code: str = Field("MAIN", pattern=r"^[A-Z0-9-]{2,20}$")

    _tz = field_validator("timezone")(_check_timezone)


class OrganisationUpdate(_OrganisationFields):
    name: str | None = Field(None, min_length=2, max_length=200)
    timezone: str | None = None
    settings: OrganisationSettingsUpdate | None = None

    _tz = field_validator("timezone")(_check_timezone)

    @model_validator(mode="after")
    def _required_not_null(self) -> "OrganisationUpdate":
        for name in ("name", "timezone"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null.")
        return self


class OrganisationRead(Schema):
    id: uuid.UUID
    name: str
    legal_name: str | None
    registration_number: str | None
    email: str | None
    phone: str | None
    currency: Literal["NAD"] | str
    timezone: str
    status: str
    settings: OrganisationSettings
    created_at: datetime
