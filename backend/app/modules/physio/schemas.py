import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.shared.schemas import Schema

MeasureType = Literal["pain_nrs", "psfs", "rom", "strength_mrc", "custom"]
Outcome = Literal["goals_met", "partly_met", "not_met", "self_discharged", "referred_on"]


class EpisodeWrite(Schema):
    condition: str = Field(min_length=2, max_length=200)
    body_region: str | None = Field(default=None, max_length=100)
    referral_source: str | None = Field(default=None, max_length=200)
    goals: str | None = Field(default=None, max_length=4000)
    planned_sessions: int | None = Field(default=None, ge=1, le=200)


class EpisodeCreate(EpisodeWrite):
    patient_id: uuid.UUID
    branch_id: uuid.UUID
    started_on: date | None = None


class SessionLink(Schema):
    encounter_id: uuid.UUID


class MeasurementInput(Schema):
    measure: MeasureType
    label: str = Field(min_length=1, max_length=150)
    side: Literal["left", "right", "both"] | None = None
    value: Decimal = Field(max_digits=8, decimal_places=2)
    unit: str | None = Field(default=None, max_length=20)  # custom measures only


class MeasurementBatch(Schema):
    encounter_id: uuid.UUID
    items: list[MeasurementInput] = Field(min_length=1, max_length=30)


class Discharge(Schema):
    outcome: Outcome
    summary: str = Field(min_length=3, max_length=4000)
    discharged_on: date | None = None


class Reason(Schema):
    reason: str = Field(min_length=3, max_length=500)


class SessionRead(Schema):
    session_number: int
    encounter_id: uuid.UUID
    started_at: datetime
    clinician_name: str


class MeasurementRead(Schema):
    id: uuid.UUID
    encounter_id: uuid.UUID
    measure: MeasureType
    label: str
    side: str | None
    value: Decimal
    unit: str
    measured_at: datetime
    status: Literal["recorded", "entered_in_error"]
    status_reason: str | None
    recorded_by_name: str


class Series(Schema):
    """One measured thing over time, e.g. right shoulder flexion, first to latest."""

    measure: MeasureType
    label: str
    side: str | None
    unit: str
    first: Decimal
    latest: Decimal
    change: Decimal
    points: list[MeasurementRead]


class EpisodeRead(Schema):
    id: uuid.UUID
    patient_id: uuid.UUID
    branch_id: uuid.UUID
    condition: str
    body_region: str | None
    referral_source: str | None
    goals: str | None
    planned_sessions: int | None
    sessions_done: int
    status: Literal["active", "discharged"]
    started_on: date
    clinician_name: str
    discharged_on: date | None
    discharge_outcome: Outcome | None
    discharge_summary: str | None


class EpisodeDetail(EpisodeRead):
    sessions: list[SessionRead]
    series: list[Series]
    measurements: list[MeasurementRead]
