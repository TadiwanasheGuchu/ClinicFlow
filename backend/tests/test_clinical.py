"""Acceptance (Phase 4): an authorised practitioner completes a consultation; signed
records cannot be silently modified; clinical access is permission-controlled and logged."""

import psycopg
import pytest

from tests.conftest import book, local_time, make_patient, verify_practitioner

SOAP = {
    "subjective": "Cough for 5 days",
    "objective": "Chest clear",
    "assessment": "Viral URTI",
    "plan": "Fluids, review if worse",
}


@pytest.fixture
def visit(clinic):
    """A checked-in appointment with the clinic's verified doctor."""
    rec = clinic["receptionist"]
    patient = make_patient(rec)
    appt = book(rec, clinic, patient["id"], local_time(1, "09:00")).json()
    assert (
        rec.post(
            f"/api/v1/appointments/{appt['id']}/status", json={"status": "checked_in"}
        ).status_code
        == 200
    )
    return {**clinic, "patient": patient, "appointment": appt}


def start(visit):
    response = visit["doctor"].post(
        "/api/v1/encounters",
        json={"patient_id": visit["patient"]["id"], "appointment_id": visit["appointment"]["id"]},
    )
    assert response.status_code == 201, response.text
    return response.json()


def signed_note(doctor, encounter_id, content=SOAP):
    note = doctor.post(
        f"/api/v1/encounters/{encounter_id}/notes",
        json={"note_type": "consultation", "content": content},
    ).json()
    signed = doctor.post(f"/api/v1/notes/{note['id']}/sign")
    assert signed.status_code == 200, signed.text
    return signed.json()


def test_complete_consultation(visit):
    doctor = visit["doctor"]
    encounter = start(visit)
    appt_url = f"/api/v1/appointments/{visit['appointment']['id']}"
    assert visit["receptionist"].get(appt_url).json()["status"] == "in_consultation"

    eid = encounter["id"]
    assert (
        doctor.post(
            f"/api/v1/encounters/{eid}/observations",
            json={
                "items": [
                    {"observation_type": "systolic_bp", "value": 128},
                    {"observation_type": "diastolic_bp", "value": 82},
                    {"observation_type": "temperature", "value": "37.9"},
                ]
            },
        ).status_code
        == 201
    )
    assert (
        doctor.post(
            f"/api/v1/encounters/{eid}/diagnoses",
            json={"description": "Acute upper respiratory infection", "code": "J06.9"},
        ).status_code
        == 201
    )
    assert (
        doctor.post(
            f"/api/v1/encounters/{eid}/referrals",
            json={
                "receiving_provider": "Dr A. Example, ENT",
                "reason": "Recurrent sinusitis for review",
            },
        ).status_code
        == 201
    )
    rx = doctor.post(
        f"/api/v1/encounters/{eid}/prescriptions",
        json={
            "items": [
                {
                    "medication": "Paracetamol",
                    "strength": "500 mg",
                    "dose": "2 tablets",
                    "frequency": "every 6 hours",
                    "duration": "3 days",
                    "quantity": "24",
                }
            ]
        },
    )
    assert rx.status_code == 201, rx.text
    assert rx.json()["prescription_number"] == "RX-000001"
    assert "HPCNA" in rx.json()["prescriber_registration"]

    # Draft notes block closing; signed notes allow it.
    draft = doctor.post(f"/api/v1/encounters/{eid}/notes", json={"content": SOAP}).json()
    assert (
        doctor.post(f"/api/v1/encounters/{eid}/close").json()["error"]["code"] == "unsigned_notes"
    )
    assert doctor.post(f"/api/v1/notes/{draft['id']}/sign").status_code == 200
    closed = doctor.post(f"/api/v1/encounters/{eid}/close")
    assert closed.status_code == 200 and closed.json()["status"] == "closed"
    assert visit["receptionist"].get(appt_url).json()["status"] == "completed"

    summary = doctor.get(f"/api/v1/patients/{visit['patient']['id']}/clinical-summary").json()
    assert {o["observation_type"] for o in summary["latest_observations"]} == {
        "systolic_bp",
        "diastolic_bp",
        "temperature",
    }
    assert summary["active_diagnoses"][0]["code"] == "J06.9"
    assert summary["encounters"][0]["status"] == "closed"

    # After closing, the record is read-only except for amendments.
    assert (
        doctor.post(
            f"/api/v1/encounters/{eid}/observations",
            json={"items": [{"observation_type": "heart_rate", "value": 80}]},
        ).json()["error"]["code"]
        == "encounter_closed"
    )


def test_audit_never_contains_clinical_content(visit):
    doctor, owner = visit["doctor"], visit["owner"]
    eid = start(visit)["id"]
    signed_note(doctor, eid)
    doctor.post(f"/api/v1/encounters/{eid}/diagnoses", json={"description": "Hypertension stage 2"})
    doctor.post(
        f"/api/v1/patients/{visit['patient']['id']}/allergies", json={"substance": "Sulfonamides"}
    )
    entries = owner.get("/api/v1/audit-logs", params={"limit": 200}).json()["items"]
    blob = str([e["details"] for e in entries]).lower()
    for secret in ("cough", "viral", "hypertension", "sulfonamides"):
        assert secret not in blob


def test_signed_notes_are_immutable(visit, app_db):
    doctor = visit["doctor"]
    eid = start(visit)["id"]
    note = signed_note(doctor, eid)
    assert len(note["content_sha256"]) == 64
    response = doctor.put(f"/api/v1/notes/{note['id']}", json={"content": {"subjective": "edited"}})
    assert response.json()["error"]["code"] == "note_signed"
    assert doctor.delete(f"/api/v1/notes/{note['id']}").status_code == 409
    # Even bypassing the API, the database refuses.
    with app_db.transaction():
        app_db.execute("SELECT set_config('app.organisation_id', %s, true)", (doctor.org_id,))
        with pytest.raises(psycopg.errors.RaiseException):
            app_db.execute(
                "UPDATE clinical_notes SET content = '{}'::jsonb WHERE id = %s", (note["id"],)
            )
    with app_db.transaction():
        app_db.execute("SELECT set_config('app.organisation_id', %s, true)", (doctor.org_id,))
        with pytest.raises(psycopg.errors.RaiseException):
            app_db.execute("DELETE FROM clinical_notes WHERE id = %s", (note["id"],))


def test_amendment_keeps_original(visit):
    doctor = visit["doctor"]
    eid = start(visit)["id"]
    original = signed_note(doctor, eid)
    doctor.post(f"/api/v1/encounters/{eid}/close")
    corrected = {**SOAP, "assessment": "Allergic rhinitis"}
    amendment = doctor.post(
        f"/api/v1/notes/{original['id']}/amend",
        json={"content": corrected, "reason": "Assessment recorded incorrectly"},
    )
    assert amendment.status_code == 201, amendment.text
    assert amendment.json()["version_number"] == 2 and amendment.json()["status"] == "draft"
    assert (
        doctor.post(
            f"/api/v1/notes/{original['id']}/amend",
            json={"content": corrected, "reason": "Second attempt"},
        ).status_code
        == 409
    )
    assert doctor.post(f"/api/v1/notes/{amendment.json()['id']}/sign").status_code == 200
    notes = {
        n["version_number"]: n for n in doctor.get(f"/api/v1/encounters/{eid}").json()["notes"]
    }
    assert notes[1]["status"] == "amended"
    assert notes[1]["content"]["assessment"] == "Viral URTI"  # original preserved
    assert notes[2]["status"] == "signed" and notes[2]["amendment_reason"]
    # Only the latest signed version can be amended.
    assert (
        doctor.post(
            f"/api/v1/notes/{notes[1]['id']}/amend", json={"content": SOAP, "reason": "Old version"}
        ).status_code
        == 409
    )


def test_only_author_edits_and_signs_drafts(visit, add_member):
    owner, doctor = visit["owner"], visit["doctor"]
    other = add_member(owner, "practitioner")
    verify_practitioner(owner, other)
    eid = start(visit)["id"]
    draft = doctor.post(f"/api/v1/encounters/{eid}/notes", json={"content": SOAP}).json()
    assert other.put(f"/api/v1/notes/{draft['id']}", json={"content": SOAP}).status_code == 403
    assert other.post(f"/api/v1/notes/{draft['id']}/sign").status_code == 403
    assert other.delete(f"/api/v1/notes/{draft['id']}").status_code == 403
    empty = doctor.post(f"/api/v1/encounters/{eid}/notes", json={"content": {}}).json()
    assert doctor.post(f"/api/v1/notes/{empty['id']}/sign").status_code == 422
    assert doctor.delete(f"/api/v1/notes/{empty['id']}").status_code == 204


def test_non_clinical_staff_cannot_read(visit, add_member):
    owner = visit["owner"]
    eid = start(visit)["id"]
    pid = visit["patient"]["id"]
    for actor in (
        visit["receptionist"],
        owner,
        add_member(owner, "auditor"),
        add_member(owner, "billing_officer"),
    ):
        assert actor.get(f"/api/v1/patients/{pid}/clinical-summary").status_code == 403
        assert actor.get(f"/api/v1/encounters/{eid}").status_code == 403
    # A practitioner whose registration is not verified has no clinical access.
    unverified = add_member(owner, "practitioner")
    assert unverified.get(f"/api/v1/patients/{pid}/clinical-summary").status_code == 403


def test_clinical_views_are_logged(visit):
    doctor, owner = visit["doctor"], visit["owner"]
    eid = start(visit)["id"]
    doctor.get(f"/api/v1/encounters/{eid}")
    doctor.get(f"/api/v1/patients/{visit['patient']['id']}/clinical-summary")
    views = owner.get("/api/v1/audit-logs", params={"action": "clinical_record.viewed"}).json()[
        "items"
    ]
    assert {v["details"]["view"] for v in views} >= {"encounter", "summary"}
    assert all(v["resource_id"] == visit["patient"]["id"] for v in views)


def test_branch_scoped_clinician(visit, add_member):
    owner = visit["owner"]
    other_branch = owner.post(
        "/api/v1/branches", json={"name": "Walvis Bay", "branch_code": "WVB"}
    ).json()
    elsewhere = add_member(owner, "practitioner", branch_id=other_branch["id"])
    verify_practitioner(owner, elsewhere)
    eid = start(visit)["id"]
    assert elsewhere.get(f"/api/v1/encounters/{eid}").status_code == 403
    summary = elsewhere.get(f"/api/v1/patients/{visit['patient']['id']}/clinical-summary").json()
    assert summary["encounters"] == []


def test_cross_tenant(visit, new_actor):
    eid = start(visit)["id"]
    other = new_actor()
    other.org_id = other.post("/api/v1/organisations", json={"name": "Elsewhere"}).json()["id"]
    assert other.get(f"/api/v1/encounters/{eid}").status_code == 403  # owner lacks clinical.read
    assert other.post(f"/api/v1/encounters/{eid}/notes", json={"content": SOAP}).status_code == 403


def test_encounter_preconditions(clinic):
    rec, doctor = clinic["receptionist"], clinic["doctor"]
    patient = make_patient(rec)
    appt = book(rec, clinic, patient["id"], local_time(1, "11:00")).json()
    body = {"patient_id": patient["id"], "appointment_id": appt["id"]}
    assert doctor.post("/api/v1/encounters", json=body).json()["error"]["code"] == "not_checked_in"
    rec.post(f"/api/v1/appointments/{appt['id']}/status", json={"status": "checked_in"})
    assert doctor.post("/api/v1/encounters", json=body).status_code == 201
    again = doctor.post("/api/v1/encounters", json=body)
    assert again.json()["error"]["code"] == "encounter_exists"
    # Unscheduled consultation (no appointment) at a branch.
    walk = doctor.post(
        "/api/v1/encounters",
        json={
            "patient_id": patient["id"],
            "branch_id": clinic["branch_id"],
            "encounter_type": "telephone",
        },
    )
    assert walk.status_code == 201


def test_allergy_states(visit):
    doctor = visit["doctor"]
    pid = visit["patient"]["id"]
    url = f"/api/v1/patients/{pid}/allergies"
    assert doctor.get(url).json()["state"] == "not_recorded"
    assert doctor.post(f"{url}/none-known").json()["state"] == "no_known_allergies"
    allergy = doctor.post(
        url, json={"substance": "Penicillin", "reaction": "Rash", "severity": "moderate"}
    ).json()
    summary = doctor.get(url).json()
    assert (
        summary["state"] == "has_allergies" and summary["allergies"][0]["substance"] == "Penicillin"
    )
    assert doctor.post(f"{url}/none-known").json()["error"]["code"] == "has_allergies"
    doctor.post(
        f"/api/v1/allergies/{allergy['id']}/status",
        json={"status": "entered_in_error", "reason": "Wrong patient"},
    )
    # The earlier "no known allergies" statement was withdrawn when an allergy was recorded.
    assert doctor.get(url).json()["state"] == "not_recorded"


def test_prescription_allergy_warning_and_immutability(visit, app_db, add_member):
    doctor, owner = visit["doctor"], visit["owner"]
    pid = visit["patient"]["id"]
    doctor.post(
        f"/api/v1/patients/{pid}/allergies", json={"substance": "Penicillin", "severity": "severe"}
    )
    eid = start(visit)["id"]
    item = {
        "medication": "Penicillin V potassium",
        "strength": "250 mg",
        "dose": "1 tablet",
        "frequency": "four times daily",
    }
    warned = doctor.post(f"/api/v1/encounters/{eid}/prescriptions", json={"items": [item]})
    assert warned.status_code == 409
    assert warned.json()["error"]["code"] == "allergy_warning"
    assert warned.json()["error"]["details"]["matches"][0]["allergy"] == "Penicillin"
    assert (
        doctor.post(
            f"/api/v1/encounters/{eid}/prescriptions",
            json={"items": [item], "acknowledge_allergy_warning": True},
        ).status_code
        == 422
    )  # reason required
    rx = doctor.post(
        f"/api/v1/encounters/{eid}/prescriptions",
        json={
            "items": [item],
            "acknowledge_allergy_warning": True,
            "acknowledgement_reason": "Allergy disputed; tolerated previously per specialist",
        },
    ).json()
    assert rx["allergy_warning"]["reason"].startswith("Allergy disputed")

    cancelled = doctor.post(
        f"/api/v1/prescriptions/{rx['id']}/cancel", json={"reason": "Changed plan"}
    )
    assert cancelled.json()["status"] == "cancelled"
    assert (
        doctor.post(
            f"/api/v1/prescriptions/{rx['id']}/cancel", json={"reason": "Again"}
        ).status_code
        == 409
    )
    refused = (psycopg.errors.RaiseException, psycopg.errors.InsufficientPrivilege)
    for statement, params in (
        ("UPDATE prescription_items SET dose = '10 tablets'", ()),
        ("UPDATE prescriptions SET status = 'issued' WHERE id = %s", (rx["id"],)),
        ("DELETE FROM prescriptions WHERE id = %s", (rx["id"],)),
    ):
        with pytest.raises(refused), app_db.transaction():
            app_db.execute("SELECT set_config('app.organisation_id', %s, true)", (doctor.org_id,))
            app_db.execute(statement, params)

    # A verified nurse can record vitals but not prescribe or sign notes.
    nurse = add_member(owner, "nurse")
    owner.put(
        f"/api/v1/members/{nurse.membership_id}/profile",
        json={
            "profession": "nurse",
            "registration_body": "Nursing Council",
            "professional_number": "RN1",
            "licence_expiry_date": "2099-01-01",
        },
    )
    owner.post(
        f"/api/v1/members/{nurse.membership_id}/profile/verify",
        json={"decision": "verified", "note": "Checked register"},
    )
    assert (
        nurse.post(
            f"/api/v1/encounters/{eid}/observations",
            json={"items": [{"observation_type": "weight", "value": 72.5}]},
        ).status_code
        == 201
    )
    assert (
        nurse.post(f"/api/v1/encounters/{eid}/prescriptions", json={"items": [item]}).status_code
        == 403
    )
    draft = nurse.post(
        f"/api/v1/encounters/{eid}/notes",
        json={"note_type": "general", "content": {"text": "Weighed"}},
    ).json()
    assert nurse.post(f"/api/v1/notes/{draft['id']}/sign").status_code == 403


def test_observation_validation_and_correction(visit):
    doctor = visit["doctor"]
    eid = start(visit)["id"]
    url = f"/api/v1/encounters/{eid}/observations"
    assert (
        doctor.post(
            url, json={"items": [{"observation_type": "heart_rate", "value": 900}]}
        ).status_code
        == 422
    )
    assert (
        doctor.post(url, json={"items": [{"observation_type": "mood", "value": 5}]}).status_code
        == 422
    )
    obs = doctor.post(
        url, json={"items": [{"observation_type": "heart_rate", "value": 88}]}
    ).json()[0]
    fixed = doctor.post(
        f"/api/v1/observations/{obs['id']}/entered-in-error", json={"reason": "Wrong patient"}
    )
    assert fixed.json()["status"] == "entered_in_error"
    summary = doctor.get(f"/api/v1/patients/{visit['patient']['id']}/clinical-summary").json()
    assert summary["latest_observations"] == []
    assert (
        doctor.post(
            f"/api/v1/encounters/{eid}/diagnoses", json={"description": "x" * 5, "code": "not-icd"}
        ).status_code
        == 422
    )
