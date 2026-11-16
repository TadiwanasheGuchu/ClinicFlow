import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import EmailStr, Field, field_validator, model_validator

from app.shared.schemas import Schema

Sex = Literal["female", "male", "intersex", "unknown"]
Channel = Literal["sms", "whatsapp", "email", "phone", "none"]
_PHONE = r"^\+?[0-9 ()-]{6,32}$"


class EmergencyContact(Schema):
    name: str = Field(min_length=2, max_length=200)
    phone: str = Field(pattern=_PHONE)
    relationship: str | None = Field(None, max_length=50)


def _check_dob(value: date | None) -> date | None:
    if value is None:
        return value
    today = date.today()
    if value > today:
        raise ValueError("Date of birth cannot be in the future.")
    if value.year < today.year - 130:
        raise ValueError("Check the date of birth.")
    return value


class _PatientFields(Schema):
    sex: Sex | None = None
    nationality: str | None = Field(None, max_length=100)
    id_number: str | None = Field(None, max_length=50)
    phone: str | None = Field(None, pattern=_PHONE)
    email: EmailStr | None = None
    address: str | None = Field(None, max_length=1000)
    emergency_contact: EmergencyContact | None = None
    preferred_channel: Channel = "sms"


class PatientCreate(_PatientFields):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date
    # Set after reviewing the possible duplicates the API returned.
    confirm_not_duplicate: bool = False

    _dob = field_validator("date_of_birth")(_check_dob)


class PatientUpdate(_PatientFields):
    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, min_length=1, max_length=100)
    date_of_birth: date | None = None
    preferred_channel: Channel | None = None  # type: ignore[assignment]
    status: Literal["active", "inactive"] | None = None

    _dob = field_validator("date_of_birth")(_check_dob)

    @model_validator(mode="after")
    def _required_not_null(self) -> "PatientUpdate":
        for name in ("first_name", "last_name", "date_of_birth", "preferred_channel", "status"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null.")
        return self


class PatientRead(Schema):
    id: uuid.UUID
    patient_number: str
    first_name: str
    last_name: str
    date_of_birth: date
    sex: str | None
    nationality: str | None
    id_number: str | None
    phone: str | None
    email: str | None
    address: str | None
    emergency_contact: EmergencyContact | None
    preferred_channel: str
    status: str
    created_at: datetime

    @field_validator("emergency_contact", mode="before")
    @classmethod
    def _empty_contact(cls, value: object) -> object:
        return value or None


class PatientSummary(Schema):
    id: uuid.UUID
    patient_number: str
    first_name: str
    last_name: str
    date_of_birth: date
    phone: str | None
    status: str
