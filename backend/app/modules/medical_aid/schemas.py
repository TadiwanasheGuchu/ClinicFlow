import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import EmailStr, Field, field_validator, model_validator

from app.shared.schemas import Schema

_ICD10 = r"^[A-TV-Z][0-9][0-9AB](\.[0-9A-Z]{1,4})?$"
ClaimStatus = Literal[
    "draft",
    "ready",
    "submitted",
    "processing",
    "accepted",
    "rejected",
    "partially_paid",
    "paid",
    "resubmission_required",
    "cancelled",
]


class FundWrite(Schema):
    name: str = Field(min_length=2, max_length=200)
    administrator: str | None = Field(None, max_length=200)
    phone: str | None = Field(None, max_length=32)
    email: EmailStr | None = None
    claims_address: str | None = Field(None, max_length=1000)
    notes: str | None = Field(None, max_length=2000)
    is_active: bool = True


class FundRead(FundWrite):
    id: uuid.UUID


class MembershipWrite(Schema):
    fund_id: uuid.UUID
    plan_name: str | None = Field(None, max_length=100)
    membership_number: str = Field(min_length=2, max_length=50)
    dependant_code: str | None = Field(None, max_length=10)
    principal_member_name: str | None = Field(None, max_length=200)
    principal_member_id_number: str | None = Field(None, max_length=50)
    effective_from: date | None = None
    effective_until: date | None = None
    is_active: bool = True


class MembershipVerify(Schema):
    method: Literal["verified_by_phone", "verified_by_card"]
    note: str | None = Field(None, max_length=500)


class MembershipRead(MembershipWrite):
    id: uuid.UUID
    patient_id: uuid.UUID
    fund_name: str
    verification_status: str
    verified_at: datetime | None


class ClaimCreate(Schema):
    invoice_id: uuid.UUID
    membership_id: uuid.UUID


def _codes(value: list[str] | None) -> list[str] | None:
    if value is None:
        return value
    import re

    cleaned = sorted({c.strip().upper() for c in value if c.strip()})
    bad = [c for c in cleaned if not re.match(_ICD10, c)]
    if bad:
        raise ValueError(f"Not valid ICD-10 codes: {', '.join(bad)}")
    return cleaned


class ClaimUpdate(Schema):
    diagnosis_codes: list[str] | None = Field(None, max_length=12)
    claimed_amount: Decimal | None = Field(None, gt=0, max_digits=12, decimal_places=2)

    _c = field_validator("diagnosis_codes")(_codes)


class ClaimTransition(Schema):
    status: ClaimStatus
    fund_reference: str | None = Field(None, max_length=100)
    submission_method: Literal["email", "fund_portal", "paper", "other"] | None = None
    approved_amount: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)
    reason: str | None = Field(None, max_length=1000)

    @model_validator(mode="after")
    def _required(self) -> "ClaimTransition":
        if self.status == "submitted" and not self.submission_method:
            raise ValueError("Record how the claim was submitted.")
        if self.status == "accepted" and self.approved_amount is None:
            raise ValueError("Record the approved amount.")
        if self.status in ("rejected", "cancelled", "resubmission_required") and not self.reason:
            raise ValueError("Give a reason.")
        return self


class Remittance(Schema):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    reference: str = Field(min_length=2, max_length=100)


class ClaimEventRead(Schema):
    id: uuid.UUID
    event_type: str
    previous_status: str | None
    new_status: str | None
    message: str | None
    details: dict[str, Any]
    actor_user_id: uuid.UUID
    created_at: datetime


class ClaimRead(Schema):
    id: uuid.UUID
    claim_number: str
    status: str
    invoice_id: uuid.UUID
    invoice_number: str | None
    patient_id: uuid.UUID
    patient_name: str
    fund_id: uuid.UUID
    fund_name: str
    membership_snapshot: dict[str, Any]
    diagnosis_codes: list[str]
    claimed_amount: Decimal
    approved_amount: Decimal | None
    paid_amount: Decimal
    patient_portion: Decimal
    fund_reference: str | None
    submission_method: str | None
    submitted_at: datetime | None
    response_at: datetime | None
    rejection_reason: str | None
    created_at: datetime


class ClaimDetail(ClaimRead):
    events: list[ClaimEventRead]
