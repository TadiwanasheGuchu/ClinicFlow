import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from app.shared.schemas import Schema

Status = Literal[
    "requested",
    "pending_confirmation",
    "confirmed",
    "checked_in",
    "waiting",
    "in_consultation",
    "completed",
    "cancelled",
    "no_show",
]
Source = Literal["reception", "phone", "walk_in"]


def _aware(value: datetime | None) -> None:
    if value is not None and value.tzinfo is None:
        raise ValueError("Times must include a timezone offset.")


class AppointmentCreate(Schema):
    patient_id: uuid.UUID
    provider_id: uuid.UUID
    branch_id: uuid.UUID
    appointment_type_id: uuid.UUID
    start_at: datetime
    booking_source: Source = "reception"
    booking_note: str | None = Field(None, max_length=500)
    # Supplying a reason requests an override of scheduling rules (needs appointments.override).
    override_reason: str | None = Field(None, min_length=3, max_length=500)

    @model_validator(mode="after")
    def _tz(self) -> "AppointmentCreate":
        _aware(self.start_at)
        return self


class Reschedule(Schema):
    start_at: datetime
    provider_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    reason: str = Field(min_length=3, max_length=500)
    override_reason: str | None = Field(None, min_length=3, max_length=500)

    @model_validator(mode="after")
    def _tz(self) -> "Reschedule":
        _aware(self.start_at)
        return self


class Cancel(Schema):
    reason: str = Field(min_length=3, max_length=500)


class StatusChange(Schema):
    status: Status
    reason: str | None = Field(None, max_length=500)


class Ref(Schema):
    id: uuid.UUID
    name: str


class PatientRef(Ref):
    patient_number: str
    date_of_birth: date


class TypeRef(Ref):
    duration_minutes: int


class AppointmentRead(Schema):
    id: uuid.UUID
    reference: str
    status: str
    start_at: datetime
    end_at: datetime
    booking_source: str
    booking_note: str | None
    cancellation_reason: str | None
    is_override: bool
    patient: PatientRef
    provider: Ref
    branch: Ref
    appointment_type: TypeRef
    created_at: datetime
    updated_at: datetime


class AppointmentEventRead(Schema):
    id: uuid.UUID
    event_type: str
    previous_status: str | None
    new_status: str | None
    actor_user_id: uuid.UUID | None
    reason: str | None
    details: dict[str, Any]
    created_at: datetime


class AppointmentDetail(AppointmentRead):
    events: list[AppointmentEventRead]
