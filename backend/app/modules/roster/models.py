"""Staff rostering: shifts per branch and staff leave.

A staff member can't be rostered on two overlapping shifts (database exclusion constraint,
migration 0007). Approved leave for a practitioner also blocks their bookable time through
a linked provider unavailability period.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey

LEAVE_TYPES = ("annual", "sick", "family", "study", "unpaid", "other")


def _same_org(column: str, target: str, name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organisation_id", column], [f"{target}.organisation_id", f"{target}.id"], name=name
    )


class Shift(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "staff_shifts"
    __table_args__ = (
        _same_org("branch_id", "branches", "fk_shifts_branch_same_org"),
        _same_org("membership_id", "organisation_memberships", "fk_shifts_member_same_org"),
        CheckConstraint("ends_at > starts_at", name="ck_shift_times"),
        CheckConstraint("ends_at - starts_at <= interval '24 hours'", name="ck_shift_length"),
        CheckConstraint("status IN ('scheduled','cancelled')", name="ck_shift_status"),
        Index("ix_shifts_org_branch_start", "organisation_id", "branch_id", "starts_at"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    branch_id: Mapped[uuid.UUID] = mapped_column()
    membership_id: Mapped[uuid.UUID] = mapped_column(index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # What the person covers on this shift, e.g. "Reception", "Treatment room".
    duty: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))


class LeaveRequest(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "staff_leave"
    __table_args__ = (
        _same_org("membership_id", "organisation_memberships", "fk_leave_member_same_org"),
        CheckConstraint("ends_on >= starts_on", name="ck_leave_dates"),
        CheckConstraint(
            "leave_type IN ('annual','sick','family','study','unpaid','other')",
            name="ck_leave_type",
        ),
        CheckConstraint(
            "status IN ('requested','approved','declined','cancelled')", name="ck_leave_status"
        ),
        Index("ix_leave_org_dates", "organisation_id", "starts_on", "ends_on"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    membership_id: Mapped[uuid.UUID] = mapped_column(index=True)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)  # inclusive
    leave_type: Mapped[str] = mapped_column(String(20))
    # Visible only to the staff member and roster managers.
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    # Set when approved leave blocks a practitioner's bookable time.
    unavailability_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("provider_unavailability.id", ondelete="SET NULL")
    )
