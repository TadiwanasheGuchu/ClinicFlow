"""Notification outbox: enqueue in the request transaction, deliver from a worker.

Delivery is at-least-once: rows are claimed with FOR UPDATE SKIP LOCKED so concurrent
workers never pick the same message, and a crash between sending and committing can at
worst repeat one message.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_sessionmaker, set_scope
from app.modules.appointments.models import Appointment
from app.modules.branches.models import Branch
from app.modules.notifications.adapters import DeliveryError, adapter_for
from app.modules.notifications.models import Notification
from app.modules.notifications.templates import MessageFields, render
from app.modules.organisations.models import Organisation
from app.modules.organisations.schemas import OrganisationSettings
from app.modules.patients.models import Patient
from app.modules.portal.models import OrganisationSlug

logger = logging.getLogger(__name__)

BACKOFF_MINUTES = (1, 5, 15, 60)
PHONE_CHANNELS = {"sms", "whatsapp"}


def _fields(db: Session, organisation: Organisation, appointment: Appointment) -> MessageFields:
    tz = ZoneInfo(organisation.timezone)
    local = appointment.start_at.astimezone(tz)
    branch = db.get_one(Branch, appointment.branch_id)
    settings = OrganisationSettings.model_validate(organisation.settings or {})
    portal_suffix = ""
    if settings.portal_enabled:
        slug = db.scalar(
            select(OrganisationSlug.slug).where(OrganisationSlug.organisation_id == organisation.id)
        )
        if slug:
            portal_suffix = f" or visit {get_settings().public_web_url}/book/{slug}"
    return MessageFields(
        practice=organisation.name,
        branch=branch.name,
        date=f"{local:%A} {local.day} {local:%b %Y}",
        time=f"{local:%H:%M}",
        reference=appointment.reference,
        practice_phone=branch.phone or organisation.phone or "the practice",
        portal_suffix=portal_suffix,
    )


def _recipient(patient: Patient) -> tuple[str | None, str | None, str | None]:
    """(channel, recipient, reason_skipped)."""
    channel = patient.preferred_channel
    if channel in ("none", "phone"):
        return channel, None, "Patient has opted out of written messages."
    if channel in PHONE_CHANNELS:
        if not patient.phone:
            return channel, None, "No mobile number on file."
        return channel, patient.phone, None
    if channel == "email":
        if not patient.email:
            return channel, None, "No email address on file."
        return channel, patient.email, None
    return channel, None, f"Unknown channel {channel}."


def enqueue(
    db: Session,
    organisation: Organisation,
    appointment: Appointment,
    event_type: str,
    *,
    actor_user_id: uuid.UUID | None,
    scheduled_for: datetime | None = None,
) -> Notification:
    patient = db.get_one(Patient, appointment.patient_id)
    channel, recipient, skipped = _recipient(patient)
    subject, body = render(event_type, _fields(db, organisation, appointment))
    notification = Notification(
        organisation_id=organisation.id,
        patient_id=patient.id,
        appointment_id=appointment.id,
        event_type=event_type,
        channel=channel if channel in ("sms", "whatsapp", "email") else "sms",
        recipient=recipient,
        subject=subject,
        body=body,
        delivery_status="skipped" if skipped else "pending",
        last_error=skipped,
        scheduled_for=scheduled_for or datetime.now(UTC),
        attempts=0,
        created_by=actor_user_id,
    )
    db.add(notification)
    return notification


def cancel_pending(db: Session, appointment_id: uuid.UUID, event_type: str | None = None) -> None:
    query = update(Notification).where(
        Notification.appointment_id == appointment_id,
        Notification.delivery_status == "pending",
    )
    if event_type:
        query = query.where(Notification.event_type == event_type)
    db.execute(query.values(delivery_status="cancelled", last_error="Superseded."))


def schedule_reminder(
    db: Session,
    organisation: Organisation,
    appointment: Appointment,
    actor_user_id: uuid.UUID | None,
) -> None:
    settings = OrganisationSettings.model_validate(organisation.settings or {})
    if not settings.reminders_enabled:
        return
    when = appointment.start_at - timedelta(hours=settings.reminder_hours_before)
    if when <= datetime.now(UTC) + timedelta(minutes=30):
        return  # Too close to the appointment; the confirmation already covers it.
    enqueue(
        db,
        organisation,
        appointment,
        "appointment_reminder",
        actor_user_id=actor_user_id,
        scheduled_for=when,
    )


def on_appointment_event(
    db: Session,
    organisation: Organisation,
    appointment: Appointment,
    event: str,
    *,
    actor_user_id: uuid.UUID | None,
) -> None:
    """Translate an appointment change into patient messages."""
    if event == "created":
        if appointment.booking_source == "walk_in":
            return
        if appointment.status == "requested":
            enqueue(
                db, organisation, appointment, "appointment_requested", actor_user_id=actor_user_id
            )
            return
        enqueue(db, organisation, appointment, "appointment_confirmed", actor_user_id=actor_user_id)
        schedule_reminder(db, organisation, appointment, actor_user_id)
    elif event == "confirmed":
        enqueue(db, organisation, appointment, "appointment_confirmed", actor_user_id=actor_user_id)
        schedule_reminder(db, organisation, appointment, actor_user_id)
    elif event == "rescheduled":
        cancel_pending(db, appointment.id, "appointment_reminder")
        enqueue(
            db, organisation, appointment, "appointment_rescheduled", actor_user_id=actor_user_id
        )
        schedule_reminder(db, organisation, appointment, actor_user_id)
    elif event == "cancelled":
        cancel_pending(db, appointment.id)
        enqueue(db, organisation, appointment, "appointment_cancelled", actor_user_id=actor_user_id)
    elif event in ("checked_in", "no_show"):
        cancel_pending(db, appointment.id, "appointment_reminder")


# --- Delivery worker ---------------------------------------------------------------


def _deliver(notification: Notification, now: datetime) -> None:
    max_attempts = get_settings().notification_max_attempts
    notification.attempts += 1
    try:
        reference = adapter_for(notification.channel).send(
            notification.recipient or "", notification.subject, notification.body
        )
    except DeliveryError as exc:
        notification.last_error = str(exc)
        if notification.attempts >= max_attempts:
            notification.delivery_status = "failed"
            notification.next_attempt_at = None
        else:
            delay = BACKOFF_MINUTES[min(notification.attempts - 1, len(BACKOFF_MINUTES) - 1)]
            notification.next_attempt_at = now + timedelta(minutes=delay)
        return
    notification.delivery_status = "sent"
    notification.provider_reference = reference
    notification.sent_at = now
    notification.last_error = None
    notification.next_attempt_at = None


def dispatch_due(limit: int = 50, now: datetime | None = None) -> dict[str, int]:
    """Deliver due messages across all organisations. Returns counts by outcome."""
    now = now or datetime.now(UTC)
    session = get_sessionmaker()()
    counts = {"sent": 0, "retrying": 0, "failed": 0}
    try:
        set_scope(session, worker=True)
        rows = session.scalars(
            select(Notification)
            .where(
                Notification.delivery_status == "pending",
                Notification.scheduled_for <= now,
                or_(Notification.next_attempt_at.is_(None), Notification.next_attempt_at <= now),
            )
            .order_by(Notification.scheduled_for)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
        for notification in rows:
            _deliver(notification, now)
            if notification.delivery_status == "sent":
                counts["sent"] += 1
            elif notification.delivery_status == "failed":
                counts["failed"] += 1
            else:
                counts["retrying"] += 1
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Notification dispatch failed")
        raise
    finally:
        session.close()
    return counts
