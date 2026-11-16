import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey


class StaffProfile(UUIDPrimaryKey, Timestamps, Base):
    """Professional details for a member. Registration must be verified by an authorised
    person before clinical permissions take effect or the member can take bookings."""

    __tablename__ = "staff_profiles"
    __table_args__ = (
        UniqueConstraint("membership_id"),
        UniqueConstraint("organisation_id", "id", name="uq_staff_profiles_org_id"),
        ForeignKeyConstraint(
            ["organisation_id", "membership_id"],
            ["organisation_memberships.organisation_id", "organisation_memberships.id"],
            ondelete="CASCADE",
            name="fk_staff_profiles_membership_same_org",
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    membership_id: Mapped[uuid.UUID] = mapped_column()
    profession: Mapped[str] = mapped_column(String(50))
    specialty: Mapped[str | None] = mapped_column(String(100))
    registration_body: Mapped[str | None] = mapped_column(String(100))
    professional_number: Mapped[str | None] = mapped_column(String(50))
    licence_expiry_date: Mapped[date | None] = mapped_column(Date)
    # unverified | verified | rejected
    registration_status: Mapped[str] = mapped_column(String(20), default="unverified")
    verified_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_note: Mapped[str | None] = mapped_column(Text)
