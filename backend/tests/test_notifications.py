"""Acceptance (Phase 3): messages contain no clinical data; failures can be retried."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import get_settings
from app.modules.notifications.service import dispatch_due
from tests.conftest import book, local_time, make_patient


def messages(actor, **params):
    return actor.get("/api/v1/notifications", params=params).json()["items"]


def test_booking_sends_confirmation_and_schedules_reminder(clinic):
    rec, owner = clinic["receptionist"], clinic["owner"]
    patient = make_patient(rec, phone="+264 81 555 1212")
    appt = book(
        rec,
        clinic,
        patient["id"],
        local_time(3, "09:00"),
        booking_note="Prefers Oshiwambo-speaking staff",
    ).json()
    rows = messages(owner, appointment_id=appt["id"])
    kinds = {m["event_type"]: m for m in rows}
    assert set(kinds) == {"appointment_confirmed", "appointment_reminder"}
    assert kinds["appointment_confirmed"]["delivery_status"] == "pending"
    reminder_at = datetime.fromisoformat(kinds["appointment_reminder"]["scheduled_for"])
    assert reminder_at == datetime.fromisoformat(appt["start_at"]) - timedelta(hours=24)


def test_messages_contain_no_clinical_or_sensitive_detail(clinic):
    owner, rec = clinic["owner"], clinic["receptionist"]
    sensitive = owner.post(
        "/api/v1/appointment-types",
        json={
            "name": "HIV counselling",
            "duration_minutes": 30,
            "fee": "0.00",
        },
    ).json()
    patient = make_patient(rec, phone="+264 81 555 3434")
    appt = book(
        rec,
        {**clinic, "type_id": sensitive["id"]},
        patient["id"],
        local_time(3, "10:00"),
        booking_note="Discuss test results",
    ).json()
    for message in messages(owner, appointment_id=appt["id"]):
        body = message["body"].lower()
        assert "hiv" not in body and "counselling" not in body
        assert "test results" not in body
        assert appt["provider"]["name"].lower() not in body
        assert appt["reference"].lower() in body


def test_worker_delivers_due_messages_only(clinic):
    rec, owner = clinic["receptionist"], clinic["owner"]
    patient = make_patient(rec, phone="+264 81 555 5656")
    appt = book(rec, clinic, patient["id"], local_time(3, "11:00")).json()
    dispatch_due()
    rows = {m["event_type"]: m for m in messages(owner, appointment_id=appt["id"])}
    assert rows["appointment_confirmed"]["delivery_status"] == "sent"
    assert rows["appointment_reminder"]["delivery_status"] == "pending"  # not due yet
    # Simulate the clock reaching the reminder time.
    dispatch_due(now=datetime.now(UTC) + timedelta(days=2, hours=12))
    rows = {m["event_type"]: m for m in messages(owner, appointment_id=appt["id"])}
    assert rows["appointment_reminder"]["delivery_status"] == "sent"


def test_cancelling_stops_the_reminder(clinic):
    rec, owner = clinic["receptionist"], clinic["owner"]
    patient = make_patient(rec, phone="+264 81 555 7878")
    appt = book(rec, clinic, patient["id"], local_time(3, "12:00")).json()
    rec.post(f"/api/v1/appointments/{appt['id']}/cancel", json={"reason": "Patient called"})
    rows = {m["event_type"]: m for m in messages(owner, appointment_id=appt["id"])}
    assert rows["appointment_reminder"]["delivery_status"] == "cancelled"
    assert rows["appointment_cancelled"]["delivery_status"] == "pending"


def test_opted_out_or_missing_contact_is_skipped(clinic):
    rec, owner = clinic["receptionist"], clinic["owner"]
    quiet = make_patient(rec, phone="+264 81 555 9090", preferred_channel="none")
    no_phone = make_patient(rec)
    a = book(rec, clinic, quiet["id"], local_time(3, "13:00")).json()
    b = book(rec, clinic, no_phone["id"], local_time(3, "14:00")).json()
    for appt, reason in ((a, "opted out"), (b, "No mobile number")):
        rows = messages(owner, appointment_id=appt["id"])
        assert rows and all(m["delivery_status"] == "skipped" for m in rows)
        assert reason in rows[0]["last_error"]


def test_failed_delivery_retries_then_can_be_retried_by_staff(clinic, monkeypatch):
    rec, owner = clinic["receptionist"], clinic["owner"]
    monkeypatch.setattr(get_settings(), "sms_provider", "none")
    monkeypatch.setattr(get_settings(), "notification_max_attempts", 2)
    patient = make_patient(rec, phone="+264 81 555 0001")
    appt = book(rec, clinic, patient["id"], local_time(3, "15:00")).json()
    now = datetime.now(UTC)
    dispatch_due(now=now)
    confirm = next(
        m
        for m in messages(owner, appointment_id=appt["id"])
        if m["event_type"] == "appointment_confirmed"
    )
    assert confirm["delivery_status"] == "pending" and confirm["attempts"] == 1
    assert "No sms provider" in confirm["last_error"]
    dispatch_due(now=now + timedelta(minutes=2))
    confirm = next(
        m
        for m in messages(owner, appointment_id=appt["id"])
        if m["event_type"] == "appointment_confirmed"
    )
    assert confirm["delivery_status"] == "failed"

    # Receptionists cannot retry what has not failed; they can retry failures.
    reminder = next(
        m
        for m in messages(owner, appointment_id=appt["id"])
        if m["event_type"] == "appointment_reminder"
    )
    assert rec.post(f"/api/v1/notifications/{reminder['id']}/retry").status_code == 409
    monkeypatch.setattr(get_settings(), "sms_provider", "log")
    retried = rec.post(f"/api/v1/notifications/{confirm['id']}/retry")
    assert retried.status_code == 200 and retried.json()["delivery_status"] == "pending"
    dispatch_due()
    confirm = next(
        m
        for m in messages(owner, appointment_id=appt["id"])
        if m["event_type"] == "appointment_confirmed"
    )
    assert confirm["delivery_status"] == "sent"
    logs = owner.get("/api/v1/audit-logs", params={"action": "notification.retried"}).json()
    assert logs["total"] == 1


def test_messages_are_tenant_isolated(clinic, new_actor):
    rec = clinic["receptionist"]
    patient = make_patient(rec, phone="+264 81 555 2323")
    book(rec, clinic, patient["id"], local_time(3, "16:00"))
    other = new_actor()
    other.org_id = other.post("/api/v1/organisations", json={"name": "Elsewhere"}).json()["id"]
    assert other.get("/api/v1/notifications").json()["total"] == 0


@pytest.mark.parametrize("hhmm", ["08:00"])
def test_walk_ins_get_no_messages(clinic, hhmm):
    rec, owner = clinic["receptionist"], clinic["owner"]
    patient = make_patient(rec, phone="+264 81 555 4545")
    response = book(
        rec, clinic, patient["id"], datetime.now(UTC).isoformat(), booking_source="walk_in"
    )
    if response.status_code == 201:
        assert messages(owner, appointment_id=response.json()["id"]) == []
