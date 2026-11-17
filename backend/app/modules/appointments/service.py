import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg.errors import ExclusionViolation
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.tenancy import TenantContext, deny
from app.modules.appointments.models import Appointment, AppointmentEvent
from app.modules.appointments.schemas import AppointmentRead, PatientRef, Ref, TypeRef
from app.modules.branches.models import Branch
from app.modules.notifications import service as notifications
from app.modules.patients.models import Patient
from app.modules.scheduling import service as scheduling
from app.modules.scheduling.models import AppointmentType, Provider
from app.shared.counters import format_number, next_value

# Allowed status transitions. Cancellation and rescheduling have their own endpoints.
TRANSITIONS: dict[str, set[str]] = {
    "requested": {"pending_confirmation", "confirmed"},
    "pending_confirmation": {"confirmed"},
    "confirmed": {"checked_in", "no_show"},
    "checked_in": {"waiting", "in_consultation"},
    "waiting": {"in_consultation"},
    "in_consultation": {"completed"},
    "completed": set(),
    "cancelled": set(),
    "no_show": set(),
}
CANCELLABLE = {"requested", "pending_confirmation", "confirmed", "checked_in", "waiting"}
RESCHEDULABLE = {"requested", "pending_confirmation", "confirmed"}

VIOLATION_MESSAGES = {
    "in_past": "The time is in the past.",
    "outside_availability": "The practitioner is not working at this branch at that time.",
    "provider_unavailable": "The practitioner is on leave or unavailable then.",
    "provider_double_booked": "The practitioner already has an appointment at that time.",
    "patient_double_booked": "The patient already has an appointment at that time.",
}


def get_appointment(db: Session, appointment_id: uuid.UUID) -> Appointment:
    appointment = db.get(Appointment, appointment_id)
    if appointment is None:
        raise NotFound("Appointment not found.")
    return appointment


def require_branch_permission(ctx: TenantContext, permission: str, branch_id: uuid.UUID) -> None:
    if not ctx.has_in_branch(permission, branch_id):
        raise deny(ctx, permission, "appointment")


def record_event(
    db: Session,
    ctx: TenantContext,
    appointment: Appointment,
    event_type: str,
    *,
    previous_status: str | None = None,
    reason: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AppointmentEvent(
            organisation_id=appointment.organisation_id,
            appointment_id=appointment.id,
            event_type=event_type,
            previous_status=previous_status,
            new_status=appointment.status,
            actor_user_id=ctx.user_id,
            reason=reason,
            details=details or {},
        )
    )
    ctx.audit(
        db,
        f"appointment.{event_type}",
        "appointment",
        appointment.id,
        branch_id=appointment.branch_id,
        details={"reference": appointment.reference, "reason": reason, **(details or {})},
    )


def _check_rules(
    db: Session,
    ctx: TenantContext,
    *,
    provider: Provider,
    branch_id: uuid.UUID,
    patient_id: uuid.UUID,
    start: datetime,
    appointment_type: AppointmentType,
    override_reason: str | None,
    allow_past: bool,
    exclude_appointment_id: uuid.UUID | None = None,
) -> tuple[datetime, datetime, list[str]]:
    end = start + timedelta(minutes=appointment_type.duration_minutes)
    blocked_until = end + timedelta(minutes=appointment_type.booking_buffer_minutes)
    violations = scheduling.rule_violations(
        db,
        provider=provider,
        branch_id=branch_id,
        patient_id=patient_id,
        start=start,
        end=end,
        blocked_until=blocked_until,
        timezone=ctx.organisation.timezone,
        allow_past=allow_past,
        exclude_appointment_id=exclude_appointment_id,
    )
    if violations:
        if override_reason is None:
            raise ValidationFailed(
                " ".join(VIOLATION_MESSAGES[v] for v in violations),
                code="scheduling_conflict",
                details={"violations": violations},
            )
        if not ctx.has_in_branch("appointments.override", branch_id):
            raise deny(ctx, "appointments.override", "appointment")
    return end, blocked_until, violations


def _validate_parties(
    db: Session, ctx: TenantContext, provider_id: uuid.UUID, branch_id: uuid.UUID
) -> tuple[Provider, Branch]:
    provider = scheduling.get_provider(db, provider_id)
    if not scheduling.provider_bookable(db, provider, ctx.organisation.timezone):
        raise ValidationFailed(
            "This practitioner cannot take bookings (booking disabled, or registration not "
            "verified or expired).",
            code="provider_not_bookable",
        )
    branch = db.get(Branch, branch_id)
    if branch is None or not branch.is_active:
        raise ValidationFailed("The branch does not exist or is inactive.")
    return provider, branch


def _flush_booking(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        if isinstance(exc.orig, ExclusionViolation):
            # Lost a race with a concurrent booking for the same time.
            raise Conflict(
                "That time was just booked by someone else. Choose another time.",
                code="slot_taken",
            ) from exc
        raise


def create(db: Session, ctx: TenantContext, data: Any) -> Appointment:
    """Staff booking."""
    require_branch_permission(ctx, "appointments.manage", data.branch_id)
    walk_in = data.booking_source == "walk_in"
    return book(db, ctx, data, status="checked_in" if walk_in else "confirmed", allow_past=walk_in)


def book(db: Session, ctx: Any, data: Any, *, status: str, allow_past: bool) -> Appointment:
    """Create an appointment after validating every scheduling rule. ``ctx`` is the staff
    TenantContext or the patient PortalContext; callers check who may book."""
    provider, _branch = _validate_parties(db, ctx, data.provider_id, data.branch_id)
    patient = db.get(Patient, data.patient_id)
    if patient is None:
        raise ValidationFailed("Patient not found.")
    if patient.status != "active":
        raise ValidationFailed("This patient record is inactive.")
    appointment_type = scheduling.get_appointment_type(db, data.appointment_type_id)
    if not appointment_type.is_active:
        raise ValidationFailed("This appointment type is no longer offered.")

    start = data.start_at.astimezone(UTC)
    end, blocked_until, violations = _check_rules(
        db,
        ctx,
        provider=provider,
        branch_id=data.branch_id,
        patient_id=patient.id,
        start=start,
        appointment_type=appointment_type,
        override_reason=getattr(data, "override_reason", None),
        allow_past=allow_past,
    )
    appointment = Appointment(
        organisation_id=ctx.organisation_id,
        reference=format_number("A", next_value(db, ctx.organisation_id, "appointment"), 7),
        branch_id=data.branch_id,
        patient_id=patient.id,
        provider_id=provider.id,
        appointment_type_id=appointment_type.id,
        start_at=start,
        end_at=end,
        blocked_until=blocked_until,
        status=status,
        booking_source=data.booking_source,
        booking_note=getattr(data, "booking_note", None),
        is_override=bool(violations),
        created_by=ctx.user_id,
    )
    db.add(appointment)
    _flush_booking(db)
    record_event(
        db,
        ctx,
        appointment,
        "created",
        details={
            "start_at": start.isoformat(),
            "provider_id": str(provider.id),
            "booking_source": data.booking_source,
            **(
                {"override": {"violations": violations, "reason": data.override_reason}}
                if violations
                else {}
            ),
        },
    )
    notifications.on_appointment_event(
        db, ctx.organisation, appointment, "created", actor_user_id=ctx.user_id
    )
    return appointment


def reschedule(db: Session, ctx: TenantContext, appointment: Appointment, data: Any) -> None:
    require_branch_permission(ctx, "appointments.manage", appointment.branch_id)
    branch_id = data.branch_id or appointment.branch_id
    if branch_id != appointment.branch_id:
        require_branch_permission(ctx, "appointments.manage", branch_id)
    move(db, ctx, appointment, data)


def move(db: Session, ctx: Any, appointment: Appointment, data: Any) -> None:
    """Reschedule after validating rules; callers check who may do it."""
    if appointment.status not in RESCHEDULABLE:
        raise Conflict(
            f"A {appointment.status.replace('_', ' ')} appointment cannot be rescheduled."
        )
    branch_id = getattr(data, "branch_id", None) or appointment.branch_id
    provider_id = getattr(data, "provider_id", None) or appointment.provider_id
    override_reason = getattr(data, "override_reason", None)
    provider, _ = _validate_parties(db, ctx, provider_id, branch_id)
    appointment_type = db.get_one(AppointmentType, appointment.appointment_type_id)
    start = data.start_at.astimezone(UTC)
    end, blocked_until, violations = _check_rules(
        db,
        ctx,
        provider=provider,
        branch_id=branch_id,
        patient_id=appointment.patient_id,
        start=start,
        appointment_type=appointment_type,
        override_reason=override_reason,
        allow_past=False,
        exclude_appointment_id=appointment.id,
    )
    before = {
        "start_at": appointment.start_at.isoformat(),
        "provider_id": str(appointment.provider_id),
        "branch_id": str(appointment.branch_id),
    }
    appointment.start_at, appointment.end_at, appointment.blocked_until = start, end, blocked_until
    appointment.provider_id, appointment.branch_id = provider.id, branch_id
    appointment.is_override = bool(violations)
    _flush_booking(db)
    record_event(
        db,
        ctx,
        appointment,
        "rescheduled",
        previous_status=appointment.status,
        reason=data.reason,
        details={
            "from": before,
            "to": {
                "start_at": start.isoformat(),
                "provider_id": str(provider.id),
                "branch_id": str(branch_id),
            },
            **(
                {"override": {"violations": violations, "reason": override_reason}}
                if violations
                else {}
            ),
        },
    )
    notifications.on_appointment_event(
        db, ctx.organisation, appointment, "rescheduled", actor_user_id=ctx.user_id
    )


def cancel(db: Session, ctx: TenantContext, appointment: Appointment, reason: str) -> None:
    require_branch_permission(ctx, "appointments.manage", appointment.branch_id)
    withdraw(db, ctx, appointment, reason)


def withdraw(db: Session, ctx: Any, appointment: Appointment, reason: str) -> None:
    """Cancel; callers check who may do it."""
    if appointment.status not in CANCELLABLE:
        raise Conflict(f"A {appointment.status.replace('_', ' ')} appointment cannot be cancelled.")
    previous = appointment.status
    appointment.status = "cancelled"
    appointment.cancellation_reason = reason
    record_event(db, ctx, appointment, "cancelled", previous_status=previous, reason=reason)
    notifications.on_appointment_event(
        db, ctx.organisation, appointment, "cancelled", actor_user_id=ctx.user_id
    )


def change_status(
    db: Session, ctx: TenantContext, appointment: Appointment, new_status: str, reason: str | None
) -> None:
    require_branch_permission(ctx, "appointments.manage", appointment.branch_id)
    if new_status == "cancelled":
        raise ValidationFailed("Use the cancel action, which requires a reason.")
    if new_status not in TRANSITIONS[appointment.status]:
        raise Conflict(
            f"Cannot change a {appointment.status.replace('_', ' ')} appointment to "
            f"{new_status.replace('_', ' ')}.",
            code="invalid_transition",
        )
    if new_status == "no_show" and datetime.now(UTC) < appointment.start_at:
        raise Conflict("An appointment can only be marked as a no-show after its start time.")
    if new_status == "completed" and not ctx.has_in_branch("clinical.write", appointment.branch_id):
        # Completing a consultation is a clinician's action.
        raise Forbidden("Only the treating practitioner can complete a consultation.")
    previous = appointment.status
    appointment.status = new_status
    record_event(db, ctx, appointment, "status_changed", previous_status=previous, reason=reason)
    if new_status in ("confirmed", "checked_in", "no_show"):
        notifications.on_appointment_event(
            db, ctx.organisation, appointment, new_status, actor_user_id=ctx.user_id
        )


def to_reads(db: Session, appointments: list[Appointment]) -> list[AppointmentRead]:
    if not appointments:
        return []

    def by_id(model: Any, ids: set[uuid.UUID]) -> dict[uuid.UUID, Any]:
        return {r.id: r for r in db.scalars(select(model).where(model.id.in_(ids)))}

    patients = by_id(Patient, {a.patient_id for a in appointments})
    providers = by_id(Provider, {a.provider_id for a in appointments})
    branches = by_id(Branch, {a.branch_id for a in appointments})
    types = by_id(AppointmentType, {a.appointment_type_id for a in appointments})
    result = []
    for a in appointments:
        p, t = patients[a.patient_id], types[a.appointment_type_id]
        result.append(
            AppointmentRead(
                id=a.id,
                reference=a.reference,
                status=a.status,
                start_at=a.start_at,
                end_at=a.end_at,
                booking_source=a.booking_source,
                booking_note=a.booking_note,
                cancellation_reason=a.cancellation_reason,
                is_override=a.is_override,
                patient=PatientRef(
                    id=p.id,
                    name=f"{p.first_name} {p.last_name}",
                    patient_number=p.patient_number,
                    date_of_birth=p.date_of_birth,
                ),
                provider=Ref(id=a.provider_id, name=providers[a.provider_id].display_name),
                branch=Ref(id=a.branch_id, name=branches[a.branch_id].name),
                appointment_type=TypeRef(id=t.id, name=t.name, duration_minutes=t.duration_minutes),
                created_at=a.created_at,
                updated_at=a.updated_at,
            )
        )
    return result
