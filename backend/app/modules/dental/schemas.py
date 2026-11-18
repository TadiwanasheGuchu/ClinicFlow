import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator

from app.modules.dental.models import CONDITIONS, SURFACES, VALID_TEETH
from app.shared.schemas import Schema

Condition = Literal[
    "sound",
    "caries",
    "filled",
    "crown",
    "root_canal",
    "missing",
    "extracted",
    "implant",
    "bridge",
    "fracture",
    "watch",
    "other",
]
assert set(Condition.__args__) == set(CONDITIONS)  # type: ignore[attr-defined]


def _tooth(value: int | None) -> int | None:
    if value is not None and value not in VALID_TEETH:
        raise ValueError("Use FDI tooth numbers: 11-48 for permanent teeth, 51-85 for primary.")
    return value


def _surfaces(value: str) -> str:
    value = value.upper().replace(" ", "")
    if any(c not in SURFACES for c in value) or len(set(value)) != len(value):
        raise ValueError("Surfaces are letters from M, O, D, B, L, P, I, each once.")
    return "".join(c for c in SURFACES if c in value)  # canonical order


class ChartEntryCreate(Schema):
    tooth: int
    surfaces: str = Field(default="", max_length=7)
    condition: Condition
    note: str | None = Field(default=None, max_length=500)

    _t = field_validator("tooth")(_tooth)
    _s = field_validator("surfaces")(_surfaces)


class ChartBatch(Schema):
    entries: list[ChartEntryCreate] = Field(min_length=1, max_length=64)


class ChartEntryRead(Schema):
    id: uuid.UUID
    encounter_id: uuid.UUID
    tooth: int
    surfaces: str
    condition: Condition
    note: str | None
    status: Literal["recorded", "entered_in_error"]
    status_reason: str | None
    recorded_by_name: str
    recorded_at: datetime


class DentalChart(Schema):
    patient_id: uuid.UUID
    # Current entries per tooth (newest first), and every entry including corrections.
    teeth: dict[int, list[ChartEntryRead]]
    history: list[ChartEntryRead]


class PlanItemWrite(Schema):
    tooth: int | None = None
    surfaces: str = Field(default="", max_length=7)
    procedure: str | None = Field(default=None, max_length=200)
    service_id: uuid.UUID | None = None
    fee: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)

    _t = field_validator("tooth")(_tooth)
    _s = field_validator("surfaces")(_surfaces)


class PlanWrite(Schema):
    patient_id: uuid.UUID
    branch_id: uuid.UUID
    title: str = Field(min_length=2, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    items: list[PlanItemWrite] = Field(min_length=1, max_length=60)


class Propose(Schema):
    valid_days: int = Field(default=30, ge=1, le=365)


class PlanDecision(Schema):
    decision: Literal["accepted", "declined"]
    note: str | None = Field(default=None, max_length=500)


class ItemDone(Schema):
    encounter_id: uuid.UUID | None = None


class Reason(Schema):
    reason: str = Field(min_length=3, max_length=500)


class PlanItemRead(Schema):
    id: uuid.UUID
    position: int
    tooth: int | None
    surfaces: str
    procedure: str
    service_id: uuid.UUID | None
    fee: Decimal
    status: Literal["planned", "done", "cancelled"]
    done_at: datetime | None
    invoice_id: uuid.UUID | None


class PlanRead(Schema):
    id: uuid.UUID
    plan_number: str
    patient_id: uuid.UUID
    branch_id: uuid.UUID
    title: str
    notes: str | None
    status: Literal["draft", "proposed", "accepted", "declined", "completed", "cancelled"]
    created_by_name: str
    created_at: datetime
    proposed_at: datetime | None
    quote_valid_until: date | None
    decided_at: datetime | None
    decision_note: str | None
    closed_at: datetime | None
    cancel_reason: str | None
    total: Decimal
    done_total: Decimal
    uninvoiced_done_total: Decimal
    items: list[PlanItemRead]


class InvoiceRef(Schema):
    invoice_id: uuid.UUID
    items: int
