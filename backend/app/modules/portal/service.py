import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core import audit
from app.core.exceptions import Conflict, NotFound, TooManyRequests, ValidationFailed
from app.modules.appointments import service as appointments
from app.modules.appointments.models import Appointment
from app.modules.audit.models import AuditLog
from app.modules.branches.models import Branch
from app.modules.patients import service as patients
from app.modules.patients.models import Patient
from app.modules.patients.schemas import PatientCreate
from app.modules.portal.context import PortalContext
from app.modules.portal.models import PatientAccount, PatientLinkCode
from app.modules.portal.schemas import PortalAppointment, SelfRegistration
from app.modules.scheduling import service as scheduling
from app.modules.scheduling.models import AppointmentType, Provider

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I
CODE_TTL = timedelta(days=7)
MAX_LINK_FAILURES_PER_HOUR = 5


def _hash(organisation_id: uuid.UUID, code: str) -> str:
    normalised = code.replace("-", "").replace(" ", "").upper()
    return hmac.new(organisation_id.bytes, normalised.encode(), hashlib.sha256).hexdigest()


def new_link_code(
    db: Session, organisation_id: uuid.UUID, patient_id: uuid.UUID, created_by: uuid.UUID
) -> tuple[str, datetime]:
    """Issue a one-time code; earlier unused codes for the patient stop working."""
    now = datetime.now(UTC)
    db.execute(
        update(PatientLinkCode)
        .where(
            PatientLinkCode.patient_id == patient_id,
            PatientLinkCode.used_at.is_(None),
            PatientLinkCode.expires_at > now,
        )
        .values(expires_at=now)
    )
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    expires = now + CODE_TTL
    db.add(
        PatientLinkCode(
            organisation_id=organisation_id,
            patient_id=patient_id,
            code_hash=_hash(organisation_id, raw),
            expires_at=expires,
            created_by=created_by,
            created_at=now,
        )
    )
    return f"{raw[:4]}-{raw[4:]}", expires


def _ensure_can_link(db: Session, ctx: PortalContext) -> None:
    if ctx.patient is not None:
        raise Conflict("Your account is already connected to a patient record.")
    revoked = db.scalar(select(PatientAccount).where(PatientAccount.user_id == ctx.user_id))
    if revoked is not None:
        raise Conflict(
            "Online access for this account was turned off. Please contact the practice.",
            code="account_revoked",
        )


def register(db: Session, ctx: PortalContext, data: SelfRegistration) -> Patient:
    _ensure_can_link(db, ctx)
    candidate = PatientCreate(
        first_name=data.first_name,
        last_name=data.last_name,
        date_of_birth=data.date_of_birth,
        phone=data.phone,
        sex=data.sex,
        email=ctx.current.user.email,
        preferred_channel=data.preferred_channel,
    )
    if patients.find_duplicates(db, candidate):
        # Never reveal whether, or which, record matched.
        raise Conflict(
            "We may already have a record for you. Ask the practice for a link code to "
            "connect your account.",
            code="record_may_exist",
        )
    candidate.confirm_not_duplicate = True
    patient = patients.register(db, ctx, candidate)  # type: ignore[arg-type]
    db.add(
        PatientAccount(
            organisation_id=ctx.organisation_id,
            patient_id=patient.id,
            user_id=ctx.user_id,
            linked_via="registration",
            status="active",
        )
    )
    ctx.audit(
        db,
        "patient.registered",
        "patient",
        patient.id,
        details={"patient_number": patient.patient_number, "self_registered": True},
    )
    ctx.audit(
        db, "portal.account_linked", "patient", patient.id, details={"method": "registration"}
    )
    return patient


def link(db: Session, ctx: PortalContext, code: str, dob: date) -> Patient:
    _ensure_can_link(db, ctx)
    since = datetime.now(UTC) - timedelta(hours=1)
    failures = (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action == "portal.link_failed",
                AuditLog.actor_user_id == ctx.user_id,
                AuditLog.timestamp >= since,
            )
        )
        or 0
    )
    if failures >= MAX_LINK_FAILURES_PER_HOUR:
        raise TooManyRequests("Too many attempts. Try again in an hour, or contact the practice.")

    now = datetime.now(UTC)
    row = db.scalar(
        select(PatientLinkCode).where(
            PatientLinkCode.code_hash == _hash(ctx.organisation_id, code),
            PatientLinkCode.used_at.is_(None),
            PatientLinkCode.expires_at > now,
        )
    )
    patient = db.get(Patient, row.patient_id) if row else None
    already = patient is not None and db.scalar(
        select(PatientAccount.id).where(PatientAccount.patient_id == patient.id)
    )
    if row is None or patient is None or patient.date_of_birth != dob or already:
        audit.record_independent(
            action="portal.link_failed",
            resource_type="patient_account",
            organisation_id=ctx.organisation_id,
            actor_user_id=ctx.user_id,
        )
        raise ValidationFailed(
            "That code and date of birth don't match our records.", code="link_failed"
        )
    row.used_at = now
    db.add(
        PatientAccount(
            organisation_id=ctx.organisation_id,
            patient_id=patient.id,
            user_id=ctx.user_id,
            linked_via="code",
            status="active",
        )
    )
    ctx.audit(db, "portal.account_linked", "patient", patient.id, details={"method": "code"})
    return patient


# --- Booking --------------------------------------------------------------------------


def _online_provider(db: Session, ctx: PortalContext, provider_id: uuid.UUID) -> Provider:
    provider = db.get(Provider, provider_id)
    if (
        provider is None
        or not provider.online_booking_enabled
        or not scheduling.provider_bookable(db, provider, ctx.organisation.timezone)
    ):
        raise NotFound("This practitioner is not available for online booking.")
    return provider


def _online_type(db: Session, type_id: uuid.UUID) -> AppointmentType:
    appointment_type = db.get(AppointmentType, type_id)
    if (
        appointment_type is None
        or not appointment_type.online_bookable
        or not appointment_type.is_active
    ):
        raise NotFound("This appointment type cannot be booked online.")
    return appointment_type


def _check_window(ctx: PortalContext, start: datetime) -> None:
    now = datetime.now(UTC)
    if start < now + timedelta(hours=ctx.settings.online_min_notice_hours):
        raise ValidationFailed(
            f"Online bookings need at least {ctx.settings.online_min_notice_hours} hours' notice. "
            "Please call the practice for sooner appointments.",
            code="too_soon",
        )
    if start > now + timedelta(days=ctx.settings.online_max_days_ahead):
        raise ValidationFailed(
            f"Online bookings open {ctx.settings.online_max_days_ahead} days ahead.", code="too_far"
        )


def slots(
    db: Session,
    ctx: PortalContext,
    provider_id: uuid.UUID,
    branch_id: uuid.UUID,
    type_id: uuid.UUID,
    day: date,
) -> list[scheduling.Window]:
    provider = _online_provider(db, ctx, provider_id)
    appointment_type = _online_type(db, type_id)
    step = ctx.settings.default_appointment_minutes
    windows = scheduling.free_slots(
        db,
        provider=provider,
        branch_id=branch_id,
        day=day,
        appointment_type=appointment_type,
        timezone=ctx.organisation.timezone,
        step_minutes=step,
    )
    now = datetime.now(UTC)
    earliest = now + timedelta(hours=ctx.settings.online_min_notice_hours)
    latest = now + timedelta(days=ctx.settings.online_max_days_ahead)
    return [w for w in windows if earliest <= w.start <= latest]


def book(db: Session, ctx: PortalContext, data: object) -> Appointment:
    assert ctx.patient is not None
    _online_provider(db, ctx, data.provider_id)  # type: ignore[attr-defined]
    _online_type(db, data.appointment_type_id)  # type: ignore[attr-defined]
    start = data.start_at.astimezone(UTC)  # type: ignore[attr-defined]
    _check_window(ctx, start)
    upcoming = (
        db.scalar(
            select(func.count())
            .select_from(Appointment)
            .where(
                Appointment.patient_id == ctx.patient.id,
                Appointment.start_at >= datetime.now(UTC),
                Appointment.status.in_(scheduling.BLOCKING_STATUSES),
            )
        )
        or 0
    )
    if upcoming >= ctx.settings.online_max_upcoming:
        raise Conflict(
            f"You already have {upcoming} upcoming appointments. Please call the practice "
            "to book more.",
            code="too_many_upcoming",
        )
    booking = SimpleNamespace(
        patient_id=ctx.patient.id,
        provider_id=data.provider_id,  # type: ignore[attr-defined]
        branch_id=data.branch_id,
        appointment_type_id=data.appointment_type_id,  # type: ignore[attr-defined]
        start_at=start,
        booking_source="online",
        booking_note=None,
        override_reason=None,
    )
    status = "confirmed" if ctx.settings.online_auto_confirm else "requested"
    return appointments.book(db, ctx, booking, status=status, allow_past=False)


def own_appointment(db: Session, ctx: PortalContext, appointment_id: uuid.UUID) -> Appointment:
    appointment = db.get(Appointment, appointment_id)
    if appointment is None or ctx.patient is None or appointment.patient_id != ctx.patient.id:
        raise NotFound("Appointment not found.")
    return appointment


def can_change(ctx: PortalContext, appointment: Appointment) -> bool:
    cutoff = appointment.start_at - timedelta(hours=ctx.settings.online_cancel_cutoff_hours)
    return appointment.status in appointments.RESCHEDULABLE and datetime.now(UTC) < cutoff


def _require_changeable(ctx: PortalContext, appointment: Appointment) -> None:
    if not can_change(ctx, appointment):
        raise Conflict(
            f"Online changes close {ctx.settings.online_cancel_cutoff_hours} hours before the "
            "appointment. Please call the practice.",
            code="change_window_closed",
        )


def cancel(db: Session, ctx: PortalContext, appointment: Appointment, reason: str | None) -> None:
    _require_changeable(ctx, appointment)
    appointments.withdraw(db, ctx, appointment, reason or "Cancelled by the patient online.")


def reschedule(
    db: Session, ctx: PortalContext, appointment: Appointment, start_at: datetime
) -> None:
    _require_changeable(ctx, appointment)
    _online_provider(db, ctx, appointment.provider_id)
    _online_type(db, appointment.appointment_type_id)
    start = start_at.astimezone(UTC)
    _check_window(ctx, start)
    appointments.move(
        db,
        ctx,
        appointment,
        SimpleNamespace(
            start_at=start, reason="Rescheduled by the patient online.", override_reason=None
        ),
    )


def to_portal(db: Session, ctx: PortalContext, rows: list[Appointment]) -> list[PortalAppointment]:
    reads = appointments.to_reads(db, rows)
    branches = {
        b.id: b
        for b in db.scalars(select(Branch).where(Branch.id.in_({r.branch_id for r in rows})))
    }
    return [
        PortalAppointment(
            id=r.id,
            reference=r.reference,
            status=r.status,
            start_at=r.start_at,
            end_at=r.end_at,
            provider_id=a.provider_id,
            branch_id=a.branch_id,
            appointment_type_id=a.appointment_type_id,
            provider_name=r.provider.name,
            branch_name=r.branch.name,
            branch_address=branches[a.branch_id].address if a.branch_id in branches else None,
            appointment_type=r.appointment_type.name,
            can_change=can_change(ctx, a),
        )
        for r, a in zip(reads, rows, strict=True)
    ]
