import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import Field, model_validator

from app.shared.schemas import Schema

LeaveType = Literal["annual", "sick", "family", "study", "unpaid", "other"]
LeaveStatus = Literal["requested", "approved", "declined", "cancelled"]


class ShiftWrite(Schema):
    branch_id: uuid.UUID
    membership_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    duty: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _times(self) -> "ShiftWrite":
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("Times must include a time zone.")
        if self.ends_at <= self.starts_at:
            raise ValueError("The shift must end after it starts.")
        if (self.ends_at - self.starts_at).total_seconds() > 24 * 3600:
            raise ValueError("A shift can't be longer than 24 hours.")
        return self


class ShiftRead(Schema):
    id: uuid.UUID
    branch_id: uuid.UUID
    membership_id: uuid.UUID
    staff_name: str
    starts_at: datetime
    ends_at: datetime
    duty: str | None
    notes: str | None
    status: Literal["scheduled", "cancelled"]


class CopyWeek(Schema):
    branch_id: uuid.UUID
    from_start: date
    to_start: date


class CopyResult(Schema):
    created: int
    skipped: int


class LeaveCreate(Schema):
    starts_on: date
    ends_on: date
    leave_type: LeaveType
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _dates(self) -> "LeaveCreate":
        if self.ends_on < self.starts_on:
            raise ValueError("Leave must end on or after the day it starts.")
        if (self.ends_on - self.starts_on).days > 366:
            raise ValueError("Record leave of more than a year as separate periods.")
        return self


class LeaveRecord(LeaveCreate):
    """Managers recording leave for someone (for example sick leave phoned in)."""

    membership_id: uuid.UUID
    approve: bool = False


class LeaveDecision(Schema):
    decision: Literal["approved", "declined"]
    note: str | None = Field(default=None, max_length=500)


class LeaveRead(Schema):
    id: uuid.UUID
    membership_id: uuid.UUID
    staff_name: str
    starts_on: date
    ends_on: date
    status: LeaveStatus
    # Type and reason are shown only to the staff member and roster managers.
    leave_type: LeaveType | None
    reason: str | None
    decided_by_name: str | None
    decided_at: datetime | None
    decision_note: str | None
    blocks_bookings: bool
    # On decision: what the leave overlaps (never cancelled automatically).
    appointments_affected: int | None = None
    shifts_affected: int | None = None


class StaffRow(Schema):
    membership_id: uuid.UUID
    name: str
    profession: str | None


class Roster(Schema):
    start: date
    end: date  # exclusive
    branch_id: uuid.UUID | None
    staff: list[StaffRow]
    shifts: list[ShiftRead]
    leave: list[LeaveRead]
    hours: dict[str, float]  # scheduled hours per membership in the period


class MyRoster(Schema):
    start: date
    end: date
    membership_id: uuid.UUID
    shifts: list[ShiftRead]
    leave: list[LeaveRead]
    branch_names: dict[str, str]
