import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from app.shared.schemas import Schema

EncounterType = Literal["consultation", "follow_up", "telephone", "procedure", "other"]
NoteType = Literal["consultation", "progress", "procedure", "general"]

# Sections each note type may contain.
NOTE_SECTIONS: dict[str, tuple[str, ...]] = {
    "consultation": ("subjective", "objective", "assessment", "plan"),
    "progress": ("subjective", "objective", "assessment", "plan"),
    "procedure": ("indication", "procedure", "findings", "plan"),
    "general": ("text",),
}

# type: (unit, min, max)
OBSERVATION_TYPES: dict[str, tuple[str, Decimal, Decimal]] = {
    "systolic_bp": ("mmHg", Decimal(50), Decimal(260)),
    "diastolic_bp": ("mmHg", Decimal(30), Decimal(160)),
    "heart_rate": ("bpm", Decimal(20), Decimal(250)),
    "temperature": ("°C", Decimal(30), Decimal(44)),
    "respiratory_rate": ("/min", Decimal(4), Decimal(80)),
    "oxygen_saturation": ("%", Decimal(50), Decimal(100)),
    "weight": ("kg", Decimal("0.3"), Decimal(400)),
    "height": ("cm", Decimal(20), Decimal(250)),
    "blood_glucose": ("mmol/L", Decimal("0.5"), Decimal(50)),
}


class EncounterCreate(Schema):
    patient_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    appointment_id: uuid.UUID | None = None
    encounter_type: EncounterType = "consultation"

    @model_validator(mode="after")
    def _branch_or_appointment(self) -> "EncounterCreate":
        if self.branch_id is None and self.appointment_id is None:
            raise ValueError("Provide branch_id or appointment_id.")
        return self


class NoteWrite(Schema):
    note_type: NoteType = "consultation"
    content: dict[str, str]

    @model_validator(mode="after")
    def _sections(self) -> "NoteWrite":
        allowed = NOTE_SECTIONS[self.note_type]
        unknown = set(self.content) - set(allowed)
        if unknown:
            raise ValueError(f"Unknown sections for a {self.note_type} note: {sorted(unknown)}")
        for key, text in self.content.items():
            if len(text) > 20000:
                raise ValueError(f"{key} is too long.")
        self.content = {k: self.content.get(k, "") for k in allowed}
        return self


class Amendment(NoteWrite):
    reason: str = Field(min_length=5, max_length=1000)


class NoteRead(Schema):
    id: uuid.UUID
    encounter_id: uuid.UUID
    note_group_id: uuid.UUID
    version_number: int
    status: str
    note_type: str
    content: dict[str, str]
    author_user_id: uuid.UUID
    author_name: str | None = None
    signed_at: datetime | None
    content_sha256: str | None
    amends_note_id: uuid.UUID | None
    amendment_reason: str | None
    created_at: datetime
    updated_at: datetime


class ObservationInput(Schema):
    observation_type: str
    value: Decimal = Field(max_digits=8, decimal_places=2)

    @model_validator(mode="after")
    def _range(self) -> "ObservationInput":
        spec = OBSERVATION_TYPES.get(self.observation_type)
        if spec is None:
            raise ValueError(f"Unknown observation type {self.observation_type}.")
        _, low, high = spec
        if not low <= self.value <= high:
            raise ValueError(f"{self.observation_type} must be between {low} and {high}.")
        return self


class ObservationBatch(Schema):
    items: list[ObservationInput] = Field(min_length=1, max_length=20)
    measured_at: datetime | None = None

    @field_validator("measured_at")
    @classmethod
    def _tz(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("Times must include a timezone offset.")
        return value


class ObservationRead(Schema):
    id: uuid.UUID
    encounter_id: uuid.UUID
    observation_type: str
    value: Decimal
    unit: str
    measured_at: datetime
    status: str
    status_reason: str | None


class StatusReason(Schema):
    reason: str = Field(min_length=3, max_length=500)


class AllergyCreate(Schema):
    substance: str = Field(min_length=2, max_length=200)
    reaction: str | None = Field(None, max_length=500)
    severity: Literal["mild", "moderate", "severe", "unknown"] = "unknown"


class AllergyStatusChange(StatusReason):
    status: Literal["inactive", "entered_in_error"]


class AllergyRead(Schema):
    id: uuid.UUID
    substance: str
    reaction: str | None
    severity: str
    status: str
    status_reason: str | None
    created_at: datetime


class AllergySummary(Schema):
    """What the patient banner shows. Never blank: 'not_recorded' is explicit."""

    state: Literal["has_allergies", "no_known_allergies", "not_recorded"]
    allergies: list[AllergyRead]
    assessed_at: datetime | None = None


_ICD10 = r"^[A-TV-Z][0-9][0-9AB](\.[0-9A-Z]{1,4})?$"


class DiagnosisCreate(Schema):
    description: str = Field(min_length=2, max_length=500)
    code: str | None = Field(None, pattern=_ICD10, description="ICD-10 code, if known")
    onset_date: date | None = None


class DiagnosisStatusChange(StatusReason):
    clinical_status: Literal["resolved", "entered_in_error", "active"]


class DiagnosisRead(Schema):
    id: uuid.UUID
    encounter_id: uuid.UUID
    code_system: str
    code: str | None
    description: str
    clinical_status: str
    status_reason: str | None
    onset_date: date | None
    created_at: datetime


class ReferralCreate(Schema):
    receiving_provider: str = Field(min_length=2, max_length=200)
    receiving_specialty: str | None = Field(None, max_length=100)
    urgency: Literal["routine", "urgent"] = "routine"
    reason: str = Field(min_length=5, max_length=5000)


class ReferralRead(Schema):
    id: uuid.UUID
    encounter_id: uuid.UUID
    receiving_provider: str
    receiving_specialty: str | None
    urgency: str
    reason: str
    status: str
    status_reason: str | None
    referring_user_id: uuid.UUID
    created_at: datetime


class PrescriptionItemInput(Schema):
    medication: str = Field(min_length=2, max_length=200)
    strength: str | None = Field(None, max_length=50)
    dosage_form: str | None = Field(None, max_length=50)
    dose: str = Field(min_length=1, max_length=100)
    frequency: str = Field(min_length=1, max_length=100)
    route: str | None = Field(None, max_length=50)
    duration: str | None = Field(None, max_length=50)
    quantity: str | None = Field(None, max_length=50)
    instructions: str | None = Field(None, max_length=1000)


class PrescriptionCreate(Schema):
    items: list[PrescriptionItemInput] = Field(min_length=1, max_length=15)
    # Set after reviewing an allergy warning returned by the API.
    acknowledge_allergy_warning: bool = False
    acknowledgement_reason: str | None = Field(None, min_length=5, max_length=500)

    @model_validator(mode="after")
    def _reason(self) -> "PrescriptionCreate":
        if self.acknowledge_allergy_warning and not self.acknowledgement_reason:
            raise ValueError("Give a reason when prescribing despite an allergy warning.")
        return self


class PrescriptionItemRead(PrescriptionItemInput):
    position: int


class PrescriptionRead(Schema):
    id: uuid.UUID
    encounter_id: uuid.UUID
    patient_id: uuid.UUID
    prescription_number: str
    prescriber_name: str
    prescriber_registration: str
    status: str
    issued_at: datetime
    cancelled_at: datetime | None
    cancel_reason: str | None
    allergy_warning: dict[str, Any] | None
    items: list[PrescriptionItemRead]


class EncounterRead(Schema):
    id: uuid.UUID
    patient_id: uuid.UUID
    branch_id: uuid.UUID
    branch_name: str
    appointment_id: uuid.UUID | None
    encounter_type: str
    status: str
    clinician_user_id: uuid.UUID
    clinician_name: str
    started_at: datetime
    ended_at: datetime | None


class EncounterDetail(EncounterRead):
    notes: list[NoteRead]
    observations: list[ObservationRead]
    diagnoses: list[DiagnosisRead]
    prescriptions: list[PrescriptionRead]
    referrals: list[ReferralRead]


class LatestObservation(Schema):
    observation_type: str
    value: Decimal
    unit: str
    measured_at: datetime


class ClinicalSummary(Schema):
    patient_id: uuid.UUID
    allergies: AllergySummary
    active_diagnoses: list[DiagnosisRead]
    latest_observations: list[LatestObservation]
    recent_prescriptions: list[PrescriptionRead]
    encounters: list[EncounterRead]
