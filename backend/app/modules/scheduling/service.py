"""Scheduling rules: provider availability, blocked periods, free slots.

Working hours are stored as local wall-clock times in the organisation's timezone.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFound
from app.modules.appointments.models import Appointment
from app.modules.members.models import Membership
from app.modules.scheduling.models import (
    AppointmentType,
    Provider,
    ProviderAvailability,
    ProviderUnavailability,
)
from app.modules.staff.models import StaffProfile
from app.modules.staff.service import is_cleared

BLOCKING_STATUSES = (
    "requested",
    "pending_confirmation",
    "confirmed",
    "checked_in",
    "waiting",
    "in_consultation",
    "completed",
)


def get_provider(db: Session, provider_id: uuid.UUID) -> Provider:
    provider = db.get(Provider, provider_id)
    if provider is None:
        raise NotFound("Practitioner not found.")
    return provider


def get_appointment_type(db: Session, type_id: uuid.UUID) -> AppointmentType:
    appointment_type = db.get(AppointmentType, type_id)
    if appointment_type is None:
        raise NotFound("Appointment type not found.")
    return appointment_type


def provider_profile(db: Session, provider: Provider) -> StaffProfile:
    return db.get_one(StaffProfile, provider.staff_profile_id)


def provider_bookable(db: Session, provider: Provider, timezone: str) -> bool:
    """Booking enabled, member active, and registration verified and current."""
    if not provider.booking_enabled:
        return False
    profile = provider_profile(db, provider)
    membership = db.get(Membership, profile.membership_id)
    return (
        membership is not None and membership.status == "active" and is_cleared(profile, timezone)
    )


@dataclass(frozen=True)
class Window:
    start: datetime
    end: datetime


def working_windows(
    db: Session, provider_id: uuid.UUID, branch_id: uuid.UUID, day: date, tz: ZoneInfo
) -> list[Window]:
    rows = db.scalars(
        select(ProviderAvailability).where(
            ProviderAvailability.provider_id == provider_id,
            ProviderAvailability.branch_id == branch_id,
            ProviderAvailability.weekday == day.weekday(),
            or_(
                ProviderAvailability.effective_from.is_(None),
                ProviderAvailability.effective_from <= day,
            ),
            or_(
                ProviderAvailability.effective_until.is_(None),
                ProviderAvailability.effective_until >= day,
            ),
        )
    ).all()
    return sorted(
        (
            Window(
                datetime.combine(day, r.start_time, tzinfo=tz),
                datetime.combine(day, r.end_time, tzinfo=tz),
            )
            for r in rows
        ),
        key=lambda w: w.start,
    )


def blocked_periods(
    db: Session,
    provider_id: uuid.UUID,
    start: datetime,
    end: datetime,
    *,
    exclude_appointment_id: uuid.UUID | None = None,
) -> list[Window]:
    """Leave plus existing appointments (including their buffer) overlapping [start, end)."""
    leave = db.scalars(
        select(ProviderUnavailability).where(
            ProviderUnavailability.provider_id == provider_id,
            ProviderUnavailability.start_at < end,
            ProviderUnavailability.end_at > start,
        )
    ).all()
    query = select(Appointment).where(
        Appointment.provider_id == provider_id,
        Appointment.status.in_(BLOCKING_STATUSES),
        Appointment.start_at < end,
        Appointment.blocked_until > start,
    )
    if exclude_appointment_id:
        query = query.where(Appointment.id != exclude_appointment_id)
    booked = db.scalars(query).all()
    return [Window(u.start_at, u.end_at) for u in leave] + [
        Window(a.start_at, a.blocked_until) for a in booked
    ]


def rule_violations(
    db: Session,
    *,
    provider: Provider,
    branch_id: uuid.UUID,
    patient_id: uuid.UUID,
    start: datetime,
    end: datetime,
    blocked_until: datetime,
    timezone: str,
    allow_past: bool = False,
    exclude_appointment_id: uuid.UUID | None = None,
) -> list[str]:
    """Scheduling rules a booking breaks. An empty list means the booking is allowed."""
    tz = ZoneInfo(timezone)
    violations: list[str] = []
    if not allow_past and start < datetime.now(UTC) - timedelta(minutes=5):
        violations.append("in_past")
    local_start = start.astimezone(tz)
    windows = working_windows(db, provider.id, branch_id, local_start.date(), tz)
    if not any(w.start <= start and end <= w.end for w in windows):
        violations.append("outside_availability")
    leave = db.scalars(
        select(ProviderUnavailability.id).where(
            ProviderUnavailability.provider_id == provider.id,
            ProviderUnavailability.start_at < end,
            ProviderUnavailability.end_at > start,
        )
    ).first()
    if leave:
        violations.append("provider_unavailable")

    def overlapping(*conditions: object) -> bool:
        query = select(Appointment.id).where(Appointment.status.in_(BLOCKING_STATUSES), *conditions)
        if exclude_appointment_id:
            query = query.where(Appointment.id != exclude_appointment_id)
        return db.scalars(query.limit(1)).first() is not None

    if overlapping(
        Appointment.provider_id == provider.id,
        Appointment.start_at < blocked_until,
        Appointment.blocked_until > start,
    ):
        violations.append("provider_double_booked")
    if overlapping(
        Appointment.patient_id == patient_id,
        and_(Appointment.start_at < end, Appointment.end_at > start),
    ):
        violations.append("patient_double_booked")
    return violations


def free_slots(
    db: Session,
    *,
    provider: Provider,
    branch_id: uuid.UUID,
    day: date,
    appointment_type: AppointmentType,
    timezone: str,
    step_minutes: int,
) -> list[Window]:
    tz = ZoneInfo(timezone)
    duration = timedelta(minutes=appointment_type.duration_minutes)
    buffer = timedelta(minutes=appointment_type.booking_buffer_minutes)
    step = timedelta(minutes=max(5, step_minutes))
    windows = working_windows(db, provider.id, branch_id, day, tz)
    if not windows:
        return []
    blocked = blocked_periods(db, provider.id, windows[0].start, windows[-1].end + buffer)
    now = datetime.now(UTC)
    slots: list[Window] = []
    for window in windows:
        cursor = window.start
        while cursor + duration <= window.end:
            end = cursor + duration
            occupied_until = end + buffer
            clash = any(b.start < occupied_until and b.end > cursor for b in blocked)
            if cursor >= now and not clash:
                slots.append(Window(cursor, end))
            cursor += step
    return slots
