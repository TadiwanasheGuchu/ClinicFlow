import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey


class Provider(UUIDPrimaryKey, Timestamps, Base):
    """A practitioner who can be booked."""

    __tablename__ = "providers"
    __table_args__ = (
        UniqueConstraint("staff_profile_id"),
        UniqueConstraint("organisation_id", "id", name="uq_providers_org_id"),
        ForeignKeyConstraint(
            ["organisation_id", "staff_profile_id"],
            ["staff_profiles.organisation_id", "staff_profiles.id"],
            name="fk_providers_profile_same_org",
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    staff_profile_id: Mapped[uuid.UUID] = mapped_column()
    display_name: Mapped[str] = mapped_column(String(200))
    booking_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    online_booking_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class ProviderAvailability(UUIDPrimaryKey, Base):
    """Recurring weekly working hours of a provider at a branch (organisation local time)."""

    __tablename__ = "provider_availability"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_availability_weekday"),
        CheckConstraint("start_time < end_time", name="ck_availability_times"),
        ForeignKeyConstraint(
            ["organisation_id", "provider_id"],
            ["providers.organisation_id", "providers.id"],
            ondelete="CASCADE",
            name="fk_availability_provider_same_org",
        ),
        ForeignKeyConstraint(
            ["organisation_id", "branch_id"],
            ["branches.organisation_id", "branches.id"],
            name="fk_availability_branch_same_org",
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    provider_id: Mapped[uuid.UUID] = mapped_column(index=True)
    branch_id: Mapped[uuid.UUID] = mapped_column()
    weekday: Mapped[int] = mapped_column(SmallInteger)  # 0 = Monday
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_until: Mapped[date | None] = mapped_column(Date)


class ProviderUnavailability(UUIDPrimaryKey, Timestamps, Base):
    """Leave and other blocked periods."""

    __tablename__ = "provider_unavailability"
    __table_args__ = (
        CheckConstraint("start_at < end_at", name="ck_unavailability_times"),
        ForeignKeyConstraint(
            ["organisation_id", "provider_id"],
            ["providers.organisation_id", "providers.id"],
            ondelete="CASCADE",
            name="fk_unavailability_provider_same_org",
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    provider_id: Mapped[uuid.UUID] = mapped_column(index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class AppointmentType(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "appointment_types"
    __table_args__ = (
        UniqueConstraint("organisation_id", "name"),
        UniqueConstraint("organisation_id", "id", name="uq_appointment_types_org_id"),
        CheckConstraint("duration_minutes BETWEEN 5 AND 480", name="ck_type_duration"),
        CheckConstraint("fee >= 0", name="ck_type_fee"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    booking_buffer_minutes: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Offered to patients in the online portal.
    online_bookable: Mapped[bool] = mapped_column(Boolean, default=False)
