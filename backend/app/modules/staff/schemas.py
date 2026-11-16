import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.shared.schemas import Schema

Profession = Literal[
    "medical_practitioner",
    "dentist",
    "physiotherapist",
    "nurse",
    "pharmacist",
    "laboratory_technician",
    "other_clinical",
    "administrative",
]
CLINICAL_PROFESSIONS = {
    "medical_practitioner",
    "dentist",
    "physiotherapist",
    "nurse",
    "pharmacist",
    "laboratory_technician",
    "other_clinical",
}


class StaffProfileUpdate(Schema):
    profession: Profession
    specialty: str | None = Field(None, max_length=100)
    registration_body: str | None = Field(None, max_length=100)
    professional_number: str | None = Field(None, max_length=50)
    licence_expiry_date: date | None = None


class Verification(Schema):
    decision: Literal["verified", "rejected"]
    note: str = Field(min_length=3, max_length=1000)


class StaffProfileRead(Schema):
    id: uuid.UUID
    membership_id: uuid.UUID
    profession: str
    specialty: str | None
    registration_body: str | None
    professional_number: str | None
    licence_expiry_date: date | None
    registration_status: str
    verified_by: uuid.UUID | None
    verified_at: datetime | None
    verification_note: str | None
    licence_current: bool
