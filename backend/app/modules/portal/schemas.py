import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import EmailStr, Field, field_validator, model_validator

from app.modules.patients.schemas import _check_dob
from app.shared.schemas import Schema

_PHONE = r"^\+?[0-9 ()-]{6,32}$"


class PortalBranch(Schema):
    id: uuid.UUID
    name: str
    address: str | None
    phone: str | None
    operating_hours: dict


class PortalProvider(Schema):
    id: uuid.UUID
    display_name: str
    specialty: str | None
    branch_ids: list[uuid.UUID]


class PortalType(Schema):
    id: uuid.UUID
    name: str
    duration_minutes: int
    fee: Decimal


class PortalPolicy(Schema):
    min_notice_hours: int
    max_days_ahead: int
    cancel_cutoff_hours: int
    auto_confirm: bool


class PortalInfo(Schema):
    name: str
    phone: str | None
    email: str | None
    branches: list[PortalBranch]
    providers: list[PortalProvider]
    appointment_types: list[PortalType]
    policy: PortalPolicy


class PortalPatient(Schema):
    first_name: str
    last_name: str
    patient_number: str
    date_of_birth: date
    phone: str | None
    email: str | None
    address: str | None
    preferred_channel: str


class PortalMe(Schema):
    email: str
    linked: bool
    patient: PortalPatient | None


class SelfRegistration(Schema):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date
    phone: str = Field(pattern=_PHONE)
    sex: Literal["female", "male", "intersex", "unknown"] | None = None
    preferred_channel: Literal["sms", "whatsapp", "email", "none"] = "sms"

    _dob = field_validator("date_of_birth")(_check_dob)


class LinkRequest(Schema):
    code: str = Field(min_length=8, max_length=12)
    date_of_birth: date


class PortalProfileUpdate(Schema):
    phone: str | None = Field(None, pattern=_PHONE)
    email: EmailStr | None = None
    address: str | None = Field(None, max_length=1000)
    preferred_channel: Literal["sms", "whatsapp", "email", "none"] | None = None

    @model_validator(mode="after")
    def _channel_not_null(self) -> "PortalProfileUpdate":
        if "preferred_channel" in self.model_fields_set and self.preferred_channel is None:
            raise ValueError("preferred_channel cannot be null.")
        return self


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Times must include a timezone offset.")
    return value


class PortalBooking(Schema):
    provider_id: uuid.UUID
    branch_id: uuid.UUID
    appointment_type_id: uuid.UUID
    start_at: datetime

    _tz = field_validator("start_at")(_aware)


class PortalReschedule(Schema):
    start_at: datetime

    _tz = field_validator("start_at")(_aware)


class PortalCancel(Schema):
    reason: str | None = Field(None, max_length=300)


class PortalAppointment(Schema):
    id: uuid.UUID
    reference: str
    status: str
    start_at: datetime
    end_at: datetime
    provider_id: uuid.UUID
    branch_id: uuid.UUID
    appointment_type_id: uuid.UUID
    provider_name: str
    branch_name: str
    branch_address: str | None
    appointment_type: str
    can_change: bool


class LinkCode(Schema):
    code: str
    expires_at: datetime


class PortalAccountStatus(Schema):
    linked: bool
    linked_via: str | None = None
    linked_at: datetime | None = None
    email: str | None = None
