"""Acceptance (Phase 2): receptionists book; conflicts are prevented (incl. concurrency);
changes are audited."""

import threading

import psycopg
import pytest

from tests.conftest import book, local_time, make_patient


def test_receptionist_books_and_change_is_audited(clinic):
    rec = clinic["receptionist"]
    patient = make_patient(rec)
    response = book(rec, clinic, patient["id"], local_time(1, "09:00"))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "confirmed"
    assert body["reference"].startswith("A-")
    assert body["patient"]["patient_number"] == patient["patient_number"]
    assert [e["event_type"] for e in body["events"]] == ["created"]
    logs = (
        clinic["owner"].get("/api/v1/audit-logs", params={"action": "appointment.created"}).json()
    )
    assert logs["total"] == 1


def test_provider_double_booking_rejected(clinic):
    rec = clinic["receptionist"]
    a, b = make_patient(rec), make_patient(rec)
    assert book(rec, clinic, a["id"], local_time(1, "10:00")).status_code == 201
    clash = book(rec, clinic, b["id"], local_time(1, "10:15"))
    assert clash.status_code == 422
    assert "provider_double_booked" in clash.json()["error"]["details"]["violations"]
    # The 10-minute buffer after a 10:00-10:30 appointment blocks 10:30 but not 10:40.
    assert book(rec, clinic, b["id"], local_time(1, "10:30")).status_code == 422
    assert book(rec, clinic, b["id"], local_time(1, "10:40")).status_code == 201


def test_patient_cannot_be_in_two_places(clinic, add_member):
    from tests.conftest import verify_practitioner

    owner, rec = clinic["owner"], clinic["receptionist"]
    second = add_member(owner, "practitioner")
    verify_practitioner(owner, second)
    provider2 = owner.post("/api/v1/providers", json={"membership_id": second.membership_id}).json()
    owner.put(
        f"/api/v1/providers/{provider2['id']}/availability",
        json={
            "windows": [
                {
                    "branch_id": clinic["branch_id"],
                    "weekday": d,
                    "start_time": "08:00",
                    "end_time": "17:00",
                }
                for d in range(7)
            ]
        },
    )
    patient = make_patient(rec)
    assert book(rec, clinic, patient["id"], local_time(1, "11:00")).status_code == 201
    other = book(
        rec, {**clinic, "provider_id": provider2["id"]}, patient["id"], local_time(1, "11:15")
    )
    assert other.status_code == 422
    assert other.json()["error"]["details"]["violations"] == ["patient_double_booked"]


def test_concurrent_requests_cannot_double_book(clinic):
    """Two simultaneous bookings for the same slot: exactly one succeeds."""
    rec = clinic["receptionist"]
    patients = [make_patient(rec), make_patient(rec)]
    start = local_time(2, "14:00")
    barrier = threading.Barrier(2)
    results: list[int] = []

    def attempt(patient_id: str) -> None:
        barrier.wait()
        results.append(book(rec, clinic, patient_id, start).status_code)

    threads = [threading.Thread(target=attempt, args=(p["id"],)) for p in patients]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results)[0] == 201
    assert sorted(results)[1] in (409, 422)  # DB constraint (race) or pre-check
    listed = rec.get(
        "/api/v1/appointments",
        params={
            "from": local_time(2, "00:00"),
            "to": local_time(3, "00:00"),
        },
    ).json()
    assert listed["total"] == 1


def test_database_rejects_overlap_even_if_app_check_is_bypassed(clinic, owner_db):
    rec = clinic["receptionist"]
    first = book(rec, clinic, make_patient(rec)["id"], local_time(3, "09:00")).json()
    second_patient = make_patient(rec)
    with pytest.raises(psycopg.errors.ExclusionViolation), owner_db.transaction():
        owner_db.execute("SELECT set_config('app.organisation_id', %s, true)", (rec.org_id,))
        owner_db.execute(
            "INSERT INTO appointments (id, organisation_id, reference, branch_id, patient_id, "
            "provider_id, appointment_type_id, start_at, end_at, blocked_until, status, "
            "booking_source, is_override, created_at, updated_at) "
            "SELECT gen_random_uuid(), organisation_id, 'X-1', branch_id, %s, provider_id, "
            "appointment_type_id, start_at, end_at, blocked_until, 'confirmed', 'reception', "
            "false, now(), now() FROM appointments WHERE id = %s",
            (second_patient["id"], first["id"]),
        )


def test_outside_availability_and_override(clinic):
    rec, owner = clinic["receptionist"], clinic["owner"]
    patient = make_patient(rec)
    late = local_time(1, "18:00")
    response = book(rec, clinic, patient["id"], late)
    assert response.status_code == 422
    assert response.json()["error"]["details"]["violations"] == ["outside_availability"]
    # Receptionists cannot override; owners (appointments.override) can, with a reason.
    assert book(rec, clinic, patient["id"], late, override_reason="Urgent").status_code == 403
    response = book(
        owner, clinic, patient["id"], late, override_reason="Doctor agreed to stay late"
    )
    assert response.status_code == 201, response.text
    assert response.json()["is_override"] is True
    created = response.json()["events"][0]
    assert created["details"]["override"]["reason"] == "Doctor agreed to stay late"


def test_leave_blocks_bookings_and_slots(clinic):
    owner, rec = clinic["owner"], clinic["receptionist"]
    leave = owner.post(
        f"/api/v1/providers/{clinic['provider_id']}/unavailability",
        json={
            "start_at": local_time(4, "08:00"),
            "end_at": local_time(4, "12:00"),
            "reason": "Leave",
        },
    )
    assert leave.status_code == 201
    response = book(rec, clinic, make_patient(rec)["id"], local_time(4, "09:00"))
    assert "provider_unavailable" in response.json()["error"]["details"]["violations"]
    slots = rec.get(
        f"/api/v1/providers/{clinic['provider_id']}/slots",
        params={
            "branch_id": clinic["branch_id"],
            "appointment_type_id": clinic["type_id"],
            "date": local_time(4, "00:00")[:10],
        },
    ).json()
    assert slots[0]["start_at"].startswith(local_time(4, "12:00")[:16])


def test_slots_exclude_booked_time_and_buffer(clinic):
    rec = clinic["receptionist"]
    params = {
        "branch_id": clinic["branch_id"],
        "appointment_type_id": clinic["type_id"],
        "date": local_time(5, "00:00")[:10],
    }
    before = rec.get(f"/api/v1/providers/{clinic['provider_id']}/slots", params=params).json()
    assert len(before) == 35  # 08:00-16:30 every 15 minutes (16:30 + 30 min = 17:00)
    book(rec, clinic, make_patient(rec)["id"], local_time(5, "09:00"))
    after = {
        s["start_at"][11:16]
        for s in rec.get(f"/api/v1/providers/{clinic['provider_id']}/slots", params=params).json()
    }
    # 09:00 booked until 09:40 (incl. buffer): 08:30 (ends 09:00 + buffer → 09:10) and
    # 08:45, 09:00, 09:15, 09:30 are gone; 09:45 is free.
    assert not {"08:30", "08:45", "09:00", "09:15", "09:30"} & after
    assert {"08:15", "09:45"} <= after


def test_reschedule_cancel_and_rebook(clinic):
    rec = clinic["receptionist"]
    patient = make_patient(rec)
    appt = book(rec, clinic, patient["id"], local_time(6, "09:00")).json()
    moved = rec.post(
        f"/api/v1/appointments/{appt['id']}/reschedule",
        json={"start_at": local_time(6, "11:00"), "reason": "Patient request"},
    )
    assert moved.status_code == 200, moved.text
    events = moved.json()["events"]
    assert events[-1]["event_type"] == "rescheduled"
    assert events[-1]["details"]["from"]["start_at"] != events[-1]["details"]["to"]["start_at"]

    # 09:00 is free again for someone else.
    assert book(rec, clinic, make_patient(rec)["id"], local_time(6, "09:00")).status_code == 201

    cancelled = rec.post(f"/api/v1/appointments/{appt['id']}/cancel", json={"reason": "Unwell"})
    assert cancelled.json()["status"] == "cancelled"
    assert book(rec, clinic, make_patient(rec)["id"], local_time(6, "11:00")).status_code == 201
    assert (
        rec.post(
            f"/api/v1/appointments/{appt['id']}/reschedule",
            json={"start_at": local_time(6, "13:00"), "reason": "x" * 3},
        ).status_code
        == 409
    )
    assert (
        rec.post(f"/api/v1/appointments/{appt['id']}/cancel", json={"reason": "again"}).status_code
        == 409
    )


def test_status_transitions(clinic):
    rec, doctor = clinic["receptionist"], clinic["doctor"]
    appt = book(rec, clinic, make_patient(rec)["id"], local_time(1, "15:00")).json()
    url = f"/api/v1/appointments/{appt['id']}/status"
    assert rec.post(url, json={"status": "completed"}).status_code == 409
    assert rec.post(url, json={"status": "no_show"}).status_code == 409  # not started yet
    assert rec.post(url, json={"status": "checked_in"}).json()["status"] == "checked_in"
    assert rec.post(url, json={"status": "waiting"}).json()["status"] == "waiting"
    assert rec.post(url, json={"status": "in_consultation"}).json()["status"] == "in_consultation"
    assert rec.post(url, json={"status": "completed"}).status_code == 403  # clinician only
    done = doctor.post(url, json={"status": "completed"})
    assert done.status_code == 200, done.text
    statuses = [(e["previous_status"], e["new_status"]) for e in done.json()["events"]]
    assert statuses[-1] == ("in_consultation", "completed")
    assert (
        rec.post(f"/api/v1/appointments/{appt['id']}/cancel", json={"reason": "late"}).status_code
        == 409
    )


def test_walk_in(clinic):
    from datetime import UTC, datetime

    rec = clinic["receptionist"]
    response = book(
        rec,
        clinic,
        make_patient(rec)["id"],
        datetime.now(UTC).isoformat(),
        booking_source="walk_in",
    )
    # Walk-ins may start "now" but must still fall inside working hours.
    if response.status_code == 422:
        assert response.json()["error"]["details"]["violations"] == ["outside_availability"]
    else:
        assert response.status_code == 201
        assert response.json()["status"] == "checked_in"


def test_unverified_provider_cannot_be_booked(clinic):
    owner, rec = clinic["owner"], clinic["receptionist"]
    doctor = clinic["doctor"]
    profile = owner.get(f"/api/v1/members/{doctor.membership_id}/profile").json()
    owner.put(
        f"/api/v1/members/{doctor.membership_id}/profile",
        json={
            **{
                k: profile[k]
                for k in ("profession", "specialty", "registration_body", "licence_expiry_date")
            },
            "professional_number": "NEW-NUMBER",
        },
    )
    response = book(rec, clinic, make_patient(rec)["id"], local_time(1, "09:00"))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "provider_not_bookable"
    provider = rec.get(f"/api/v1/providers/{clinic['provider_id']}").json()
    assert provider["credentials_current"] is False


def test_appointment_events_are_append_only(clinic, app_db):
    rec = clinic["receptionist"]
    book(rec, clinic, make_patient(rec)["id"], local_time(1, "12:00"))
    with app_db.transaction():
        app_db.execute("SELECT set_config('app.organisation_id', %s, true)", (rec.org_id,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            app_db.execute("DELETE FROM appointment_events")


def test_listing_requires_range_and_is_tenant_scoped(clinic, new_actor):
    rec = clinic["receptionist"]
    appt = book(rec, clinic, make_patient(rec)["id"], local_time(1, "13:00")).json()
    assert rec.get("/api/v1/appointments").status_code == 422
    other = new_actor()
    other.org_id = other.post("/api/v1/organisations", json={"name": "Elsewhere"}).json()["id"]
    assert other.get(f"/api/v1/appointments/{appt['id']}").status_code == 404
    assert (
        other.post(
            f"/api/v1/appointments/{appt['id']}/cancel", json={"reason": "sabotage"}
        ).status_code
        == 404
    )
    # Booking another organisation's patient or practitioner fails.
    other_patient = make_patient(other)
    response = book(other, clinic, other_patient["id"], local_time(1, "13:00"))
    assert response.status_code in (404, 422)


def test_branch_scoped_staff_only_see_their_branch(clinic, add_member):
    owner = clinic["owner"]
    rec = clinic["receptionist"]
    second = owner.post(
        "/api/v1/branches", json={"name": "Walvis Bay", "branch_code": "WVB"}
    ).json()
    local = add_member(owner, "receptionist", branch_id=second["id"])
    book(rec, clinic, make_patient(rec)["id"], local_time(1, "14:00"))
    listed = local.get(
        "/api/v1/appointments",
        params={
            "from": local_time(1, "00:00"),
            "to": local_time(2, "00:00"),
        },
    ).json()
    assert listed["total"] == 0
    response = book(local, clinic, make_patient(local)["id"], local_time(1, "16:00"))
    assert response.status_code == 403


def test_database_conflict_is_reported_as_slot_taken(clinic, monkeypatch):
    """If two requests pass the application check together, the database constraint
    decides; the loser gets a clear 409 rather than a server error."""
    from app.modules.scheduling import service as scheduling

    rec = clinic["receptionist"]
    assert book(rec, clinic, make_patient(rec)["id"], local_time(7, "09:00")).status_code == 201
    monkeypatch.setattr(scheduling, "rule_violations", lambda *a, **k: [])
    response = book(rec, clinic, make_patient(rec)["id"], local_time(7, "09:10"))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "slot_taken"
