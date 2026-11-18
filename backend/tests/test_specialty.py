"""Phase 6 — specialty extensions (dental, physiotherapy). Optional per organisation, built on
the core record, with the same credential-gated permissions, auditing and immutability."""

import psycopg
import pytest

from tests.conftest import verify_practitioner
from tests.test_clinical import start, visit  # noqa: F401  (fixture)


def enable(owner, *modules: str) -> None:
    r = owner.patch("/api/v1/organisation", json={"settings": {"specialty_modules": list(modules)}})
    assert r.status_code == 200, r.text


@pytest.fixture
def dental(visit):  # noqa: F811
    enable(visit["owner"], "dental")
    return {**visit, "encounter": start(visit)}


def chart(actor, encounter_id, entries):
    return actor.post(f"/api/v1/encounters/{encounter_id}/dental-chart", json={"entries": entries})


def test_modules_are_off_until_enabled(visit):  # noqa: F811
    doctor, pid = visit["doctor"], visit["patient"]["id"]
    off = doctor.get(f"/api/v1/patients/{pid}/dental-chart")
    assert off.status_code == 403 and off.json()["error"]["code"] == "module_not_enabled"
    assert doctor.get(f"/api/v1/patients/{pid}/physio-episodes").status_code == 403
    enable(visit["owner"], "physiotherapy")
    assert doctor.get(f"/api/v1/patients/{pid}/physio-episodes").status_code == 200
    assert doctor.get(f"/api/v1/patients/{pid}/dental-chart").status_code == 403
    bad = visit["owner"].patch(
        "/api/v1/organisation", json={"settings": {"specialty_modules": ["oncology"]}}
    )
    assert bad.status_code == 422


def test_tooth_chart(dental):
    doctor, eid, pid = dental["doctor"], dental["encounter"]["id"], dental["patient"]["id"]
    assert chart(doctor, eid, [{"tooth": 19, "condition": "caries"}]).status_code == 422
    assert (
        chart(doctor, eid, [{"tooth": 16, "surfaces": "X", "condition": "caries"}]).status_code
        == 422
    )
    r = chart(
        doctor,
        eid,
        [
            {"tooth": 16, "surfaces": "dom", "condition": "caries"},
            {"tooth": 46, "condition": "missing"},
            {"tooth": 75, "condition": "sound"},
        ],
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["teeth"]["16"][0]["surfaces"] == "MOD"  # canonical order
    assert set(body["teeth"]) == {"16", "46", "75"}
    wrong = body["teeth"]["46"][0]["id"]
    fixed = doctor.post(
        f"/api/v1/dental-chart/{wrong}/entered-in-error", json={"reason": "Wrong tooth"}
    )
    assert "46" not in fixed.json()["teeth"]
    kept = next(e for e in fixed.json()["history"] if e["id"] == wrong)
    assert kept["status"] == "entered_in_error"
    # Reception can't see the chart; every view is audited without clinical content.
    assert dental["receptionist"].get(f"/api/v1/patients/{pid}/dental-chart").status_code == 403
    entries = dental["owner"].get("/api/v1/audit-logs", params={"limit": 200}).json()["items"]
    assert any(e["action"] == "dental_chart.recorded" for e in entries)
    text = str([e["details"] for e in entries])
    assert "caries" not in text and "MOD" not in text


def test_treatment_plan_quotation_and_invoice(dental, app_db, add_member):
    doctor, owner, rec = dental["doctor"], dental["owner"], dental["receptionist"]
    service = owner.post(
        "/api/v1/services",
        json={
            "code": "D8341",
            "name": "Composite filling, 3 surfaces",
            "unit_price": "950.00",
            "tax_category": "exempt",
        },
    ).json()
    body = {
        "patient_id": dental["patient"]["id"],
        "branch_id": dental["branch_id"],
        "title": "Restorative treatment",
        "items": [
            {"tooth": 16, "surfaces": "MOD", "service_id": service["id"]},
            {"tooth": 46, "procedure": "Implant consultation", "fee": "450.00"},
        ],
    }
    created = doctor.post("/api/v1/dental-plans", json=body)
    assert created.status_code == 201, created.text
    plan = created.json()
    assert plan["plan_number"].startswith("TP-")
    assert plan["items"][0]["procedure"] == "Composite filling, 3 surfaces"
    assert plan["total"] == "1400.00"
    url = f"/api/v1/dental-plans/{plan['id']}"
    assert doctor.post(f"{url}/items/{plan['items'][0]['id']}/done", json={}).status_code == 409
    quote = doctor.post(f"{url}/propose", json={"valid_days": 30}).json()
    assert quote["status"] == "proposed" and quote["quote_valid_until"]
    # A quotation is frozen: not editable through the API or the database.
    assert doctor.put(url, json=body).json()["error"]["code"] == "plan_not_draft"
    with app_db.transaction():
        app_db.execute("SELECT set_config('app.organisation_id', %s, true)", (owner.org_id,))
        with pytest.raises(psycopg.errors.RaiseException):
            app_db.execute("UPDATE dental_plan_items SET fee = 1 WHERE plan_id = %s", (plan["id"],))
    accepted = doctor.post(
        f"{url}/decide", json={"decision": "accepted", "note": "Signed quotation"}
    )
    assert accepted.json()["status"] == "accepted"
    filling, consult = (i["id"] for i in plan["items"])
    done = doctor.post(
        f"{url}/items/{filling}/done", json={"encounter_id": dental["encounter"]["id"]}
    )
    assert done.json()["done_total"] == "950.00"
    assert (
        doctor.post(f"{url}/cancel", json={"reason": "Changed mind"}).json()["error"]["code"]
        == "has_done_items"
    )

    # Invoicing needs clinical access to the plan and billing rights: neither the doctor
    # (no billing.manage) nor reception (no clinical access) can do it alone.
    assert doctor.post(f"{url}/invoice").status_code == 403
    assert rec.post(f"{url}/invoice").status_code == 403
    biller = add_member(owner, "practitioner", "receptionist")
    verify_practitioner(owner, biller)
    inv = biller.post(f"{url}/invoice")
    assert inv.status_code == 200, inv.text
    invoice = owner.get(f"/api/v1/invoices/{inv.json()['invoice_id']}").json()
    assert invoice["status"] == "draft" and invoice["total"] == "950.00"
    assert biller.post(f"{url}/invoice").json()["error"]["code"] == "nothing_to_invoice"
    completed = doctor.post(f"{url}/items/{consult}/cancel").json()
    assert completed["status"] == "completed"


def test_physiotherapy_episode(visit):  # noqa: F811
    enable(visit["owner"], "physiotherapy")
    doctor = visit["doctor"]
    encounter = start(visit)
    created = doctor.post(
        "/api/v1/physio-episodes",
        json={
            "patient_id": visit["patient"]["id"],
            "branch_id": visit["branch_id"],
            "condition": "Right shoulder impingement",
            "body_region": "Shoulder",
            "goals": "Reach overhead shelf without pain",
            "planned_sessions": 6,
        },
    )
    assert created.status_code == 201, created.text
    episode = created.json()
    url = f"/api/v1/physio-episodes/{episode['id']}"
    bad = doctor.post(
        f"{url}/measurements",
        json={
            "encounter_id": encounter["id"],
            "items": [{"measure": "pain_nrs", "label": "Pain", "value": "11"}],
        },
    )
    assert bad.status_code == 422
    first = doctor.post(
        f"{url}/measurements",
        json={
            "encounter_id": encounter["id"],
            "items": [
                {"measure": "pain_nrs", "label": "Pain at rest", "value": "7"},
                {"measure": "rom", "label": "Shoulder flexion", "side": "right", "value": "95"},
            ],
        },
    )
    assert first.status_code == 201, first.text
    assert first.json()["sessions_done"] == 1  # measuring links the session
    # A later session (second consultation) shows progress.
    doctor.post(
        f"/api/v1/encounters/{encounter['id']}/notes",
        json={"note_type": "general", "content": {"text": "Session 1"}},
    )
    note = doctor.get(f"/api/v1/encounters/{encounter['id']}").json()["notes"][0]
    doctor.post(f"/api/v1/notes/{note['id']}/sign")
    assert doctor.post(f"/api/v1/encounters/{encounter['id']}/close").status_code == 200
    second = doctor.post(
        "/api/v1/encounters",
        json={"patient_id": visit["patient"]["id"], "branch_id": visit["branch_id"]},
    ).json()
    later = doctor.post(
        f"{url}/measurements",
        json={
            "encounter_id": second["id"],
            "items": [
                {"measure": "pain_nrs", "label": "Pain at rest", "value": "3"},
                {"measure": "rom", "label": "Shoulder flexion", "side": "right", "value": "150"},
            ],
        },
    ).json()
    assert later["sessions_done"] == 2
    series = {s["label"]: s for s in later["series"]}
    assert series["Pain at rest"]["change"] == "-4.00"
    assert series["Shoulder flexion"]["latest"] == "150.00"
    wrong = later["measurements"][-1]["id"]
    corrected = doctor.post(
        f"/api/v1/physio-measurements/{wrong}/entered-in-error",
        json={"reason": "Measured the wrong side"},
    ).json()
    assert len({s["label"]: s for s in corrected["series"]}["Shoulder flexion"]["points"]) == 1

    done = doctor.post(
        f"{url}/discharge", json={"outcome": "goals_met", "summary": "Full function"}
    )
    assert done.json()["status"] == "discharged"
    again = doctor.post(
        f"{url}/measurements",
        json={
            "encounter_id": second["id"],
            "items": [{"measure": "psfs", "label": "Lifting", "value": "9"}],
        },
    )
    assert again.json()["error"]["code"] == "discharged"
    assert visit["receptionist"].get(url).status_code == 403


def test_specialty_cross_tenant(dental, new_actor, add_member):
    eid = dental["encounter"]["id"]
    entry = chart(dental["doctor"], eid, [{"tooth": 11, "condition": "crown"}]).json()["teeth"][
        "11"
    ][0]["id"]
    other = new_actor()
    other.org_id = other.post("/api/v1/organisations", json={"name": "Elsewhere"}).json()["id"]
    enable(other, "dental")
    clinician = add_member(other, "practitioner")
    verify_practitioner(other, clinician)
    assert (
        clinician.get(f"/api/v1/patients/{dental['patient']['id']}/dental-chart").status_code == 404
    )
    assert (
        clinician.post(
            f"/api/v1/dental-chart/{entry}/entered-in-error", json={"reason": "xxxxx"}
        ).status_code
        == 404
    )


def test_clinicians_can_read_but_not_edit_the_price_list(visit):  # noqa: F811
    doctor = visit["doctor"]
    assert doctor.get("/api/v1/services").status_code == 200
    created = doctor.post(
        "/api/v1/services",
        json={"code": "X1", "name": "Something", "unit_price": "1.00", "tax_category": "exempt"},
    )
    assert created.status_code == 403
    assert doctor.get("/api/v1/invoices").status_code == 403
