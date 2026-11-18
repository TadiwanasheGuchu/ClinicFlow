import uuid
from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field, model_validator

from app.shared.schemas import Schema

OrderStatus = Literal[
    "requested", "collected", "sent", "processing", "completed", "reviewed", "cancelled"
]
# Progress steps a user can move an order to (review and cancellation have own endpoints).
ProgressStatus = Literal["collected", "sent", "processing", "completed"]
ResultFlag = Literal["normal", "low", "high", "critical_low", "critical_high", "abnormal", "none"]


# --- Configuration -----------------------------------------------------------------------


class LaboratoryWrite(Schema):
    name: str = Field(min_length=2, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    notes: str | None = Field(default=None, max_length=2000)
    is_active: bool = True


class LaboratoryRead(Schema):
    id: uuid.UUID
    name: str
    phone: str | None
    email: str | None
    notes: str | None
    is_active: bool


class LabTestWrite(Schema):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=2, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    specimen_type: str | None = Field(default=None, max_length=100)
    is_active: bool = True


class LabTestRead(Schema):
    id: uuid.UUID
    code: str
    name: str
    category: str | None
    specimen_type: str | None
    is_active: bool


# --- Orders ------------------------------------------------------------------------------


class OrderItemCreate(Schema):
    """Either a test from the practice's list (``test_id``) or a test named by hand."""

    test_id: uuid.UUID | None = None
    test_name: str | None = Field(default=None, max_length=200)
    specimen_type: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def _one_source(self) -> "OrderItemCreate":
        if self.test_id is None and not self.test_name:
            raise ValueError("Choose a test or enter its name.")
        if self.test_name is not None and len(self.test_name) < 2:
            raise ValueError("Test name is too short.")
        return self


class LabOrderCreate(Schema):
    items: list[OrderItemCreate] = Field(min_length=1, max_length=30)
    laboratory_id: uuid.UUID | None = None
    urgency: Literal["routine", "urgent"] = "routine"
    clinical_information: str | None = Field(default=None, max_length=2000)


class ProgressChange(Schema):
    status: ProgressStatus
    external_reference: str | None = Field(default=None, max_length=100)
    laboratory_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=500)


class CancelOrder(Schema):
    reason: str = Field(min_length=3, max_length=500)


class ReviewOrder(Schema):
    comment: str | None = Field(default=None, max_length=2000)


class ResultCreate(Schema):
    item_id: uuid.UUID
    analyte: str | None = Field(default=None, max_length=200)
    value: str = Field(min_length=1, max_length=200)
    unit: str | None = Field(default=None, max_length=40)
    reference_range: str | None = Field(default=None, max_length=100)
    flag: ResultFlag = "none"
    comment: str | None = Field(default=None, max_length=2000)


class ResultBatch(Schema):
    results: list[ResultCreate] = Field(min_length=1, max_length=60)


class ResultRead(Schema):
    id: uuid.UUID
    item_id: uuid.UUID
    analyte: str
    value: str
    unit: str | None
    reference_range: str | None
    flag: ResultFlag
    comment: str | None
    status: Literal["final", "entered_in_error"]
    status_reason: str | None
    recorded_by_name: str
    recorded_at: datetime


class OrderItemRead(Schema):
    id: uuid.UUID
    position: int
    test_code: str | None
    test_name: str
    specimen_type: str | None
    resulted: bool
    results: list[ResultRead]


class OrderEventRead(Schema):
    from_status: str | None
    to_status: str
    actor_name: str
    occurred_at: datetime
    note: str | None


class LabOrderSummary(Schema):
    id: uuid.UUID
    order_number: str
    patient_id: uuid.UUID
    patient_name: str
    patient_number: str
    branch_id: uuid.UUID
    encounter_id: uuid.UUID
    status: OrderStatus
    urgency: Literal["routine", "urgent"]
    requested_at: datetime
    requested_by: uuid.UUID
    requested_by_name: str
    laboratory_name: str | None
    tests: list[str]
    abnormal_results: int


class LabOrderDetail(LabOrderSummary):
    clinical_information: str | None
    laboratory_id: uuid.UUID | None
    external_reference: str | None
    collected_at: datetime | None
    sent_at: datetime | None
    completed_at: datetime | None
    reviewed_at: datetime | None
    reviewed_by_name: str | None
    review_comment: str | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    items: list[OrderItemRead]
    events: list[OrderEventRead]
