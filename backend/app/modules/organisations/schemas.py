import uuid
from datetime import datetime
from decimal import Decimal
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
    # Patient portal and reminders (Phase 3)
    portal_enabled: bool = False
    online_auto_confirm: bool = True
    online_min_notice_hours: int = Field(2, ge=0, le=168)
    online_max_days_ahead: int = Field(60, ge=1, le=365)
    online_cancel_cutoff_hours: int = Field(24, ge=0, le=168)
    online_max_upcoming: int = Field(3, ge=1, le=20)
    reminder_hours_before: int = Field(24, ge=1, le=168)
    reminders_enabled: bool = True
    # Billing (Phase 5). VAT treatment of medical services must be confirmed with the
    # practice's accountant; the default is not VAT-registered.
    vat_registered: bool = False
    vat_rate: Decimal = Field(Decimal("15.00"), ge=0, le=100, max_digits=5, decimal_places=2)
    vat_number: str | None = Field(None, max_length=30)
    invoice_due_days: int = Field(30, ge=0, le=365)


class OrganisationSettingsUpdate(Schema):
    patient_number_prefix: str | None = Field(None, pattern=r"^[A-Z]{1,5}$")
    invoice_number_prefix: str | None = Field(None, pattern=r"^[A-Z]{1,5}$")
    default_appointment_minutes: int | None = Field(None, ge=5, le=240)
    booking_buffer_minutes: int | None = Field(None, ge=0, le=120)
    portal_enabled: bool | None = None
    online_auto_confirm: bool | None = None
    online_min_notice_hours: int | None = Field(None, ge=0, le=168)
    online_max_days_ahead: int | None = Field(None, ge=1, le=365)
    online_cancel_cutoff_hours: int | None = Field(None, ge=0, le=168)
    online_max_upcoming: int | None = Field(None, ge=1, le=20)
    reminder_hours_before: int | None = Field(None, ge=1, le=168)
    reminders_enabled: bool | None = None
    vat_registered: bool | None = None
    vat_rate: Decimal | None = Field(None, ge=0, le=100, max_digits=5, decimal_places=2)
    vat_number: str | None = Field(None, max_length=30)
    invoice_due_days: int | None = Field(None, ge=0, le=365)


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
    # Address of the patient portal: /book/<slug>
    slug: str | None = Field(None, pattern=r"^[a-z0-9](?:[a-z0-9-]{1,58}[a-z0-9])$")
    timezone: str | None = None
    settings: OrganisationSettingsUpdate | None = None

    _tz = field_validator("timezone")(_check_timezone)

    @model_validator(mode="after")
    def _required_not_null(self) -> "OrganisationUpdate":
        for name in ("name", "timezone", "slug"):
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
    slug: str | None = None
    created_at: datetime
