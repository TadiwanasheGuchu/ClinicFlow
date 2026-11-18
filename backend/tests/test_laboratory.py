"""Phase 6 — laboratory orders and results (manual workflow).

A practitioner requests tests from a consultation; a laboratory technician records
collection, dispatch and results; a clinician reviews them. Results are never edited, only
marked as entered in error, and a change after review sends the order back for review."""

import psycopg
import pytest

from tests.conftest import verify_practitioner
from tests.test_clinical import signed_note, start, visit  # noqa: F401  (fixture)

FBC = [
    {"analyte": "Haemoglobin", "value": "10.2", "unit": "g/dL", "reference_range": "12.0-15.5",
     "flag": "low"},
    {"analyte": "White cell count", "value": "7.1", "unit": "x10^9/L",
     "reference_range": "4.0-11.0", "flag": "normal"},
]  # fmt: skip


@pytest.fixture
def lab(visit, add_member):  # noqa: F811
    owner = visit["owner"]
    tests = {}
    for code, name, specimen in (
        ("FBC", "Full blood count", "EDTA blood"),
        ("HBA1C", "HbA1c", "EDTA blood"),
    ):
        response = owner.post(
            "/api/v1/laboratory-tests",
            json={"code": code, "name": name, "category": "Haematology", "specimen_type": specimen},
        )
        assert response.status_code == 201, response.text
        tests[code] = response.json()
    laboratory = owner.post("/api/v1/laboratories", json={"name": "Example Pathology Erongo"})
    assert laboratory.status_code == 201, laboratory.text
    technician = add_member(owner, "lab_technician")
    verify_practitioner(owner, technician)
    encounter = start(visit)
    return {
        **visit,
        "tests": tests,
        "laboratory": laboratory.json(),
        "technician": technician,
        "encounter": encounter,
    }


def order(lab, **extra):
    response = lab["doctor"].post(
        f"/api/v1/encounters/{lab['encounter']['id']}/lab-orders",
        json={
            "items": [
                {"test_id": lab["tests"]["FBC"]["id"]},
                {"test_name": "Urine microscopy", "specimen_type": "Mid-stream urine"},
            ],
            "laboratory_id": lab["laboratory"]["id"],
            "urgency": "urgent",
            "clinical_information": "Tiredness for 3 weeks",
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def move(actor, order_id, status, **extra):
    return actor.post(f"/api/v1/lab-orders/{order_id}/progress", json={"status": status, **extra})


def results(actor, order_id, entries):
    return actor.post(f"/api/v1/lab-orders/{order_id}/results", json={"results": entries})


def test_full_workflow(lab):
    doctor, tech = lab["doctor"], lab["technician"]
    created = order(lab)
    assert created["order_number"].startswith("LAB-")
    assert created["status"] == "requested"
    assert [i["test_name"] for i in created["items"]] == ["Full blood count", "Urine microscopy"]
    assert created["items"][0]["test_code"] == "FBC"
    assert created["items"][0]["specimen_type"] == "EDTA blood"
    oid = created["id"]
    fbc, urine = (i["id"] for i in created["items"])

    assert move(tech, oid, "collected").json()["collected_at"]
    sent = move(tech, oid, "sent", external_reference="EPE-55120").json()
    assert sent["external_reference"] == "EPE-55120"
    recorded = results(
        tech,
        oid,
        [{**r, "item_id": fbc} for r in FBC]
        + [{"item_id": urine, "value": "No cells seen", "flag": "normal"}],
    )
    assert recorded.status_code == 201, recorded.text
    detail = recorded.json()
    assert detail["abnormal_results"] == 1
    assert all(i["resulted"] for i in detail["items"])
    assert detail["items"][1]["results"][0]["analyte"] == "Urine microscopy"
    assert move(tech, oid, "completed").json()["status"] == "completed"

    # The requesting doctor sees it on their review list.
    to_review = doctor.get("/api/v1/lab-orders", params={"group": "to_review", "mine": True}).json()
    assert [o["id"] for o in to_review["items"]] == [oid]
    assert to_review["items"][0]["tests"] == ["Full blood count", "Urine microscopy"]

    reviewed = doctor.post(f"/api/v1/lab-orders/{oid}/review", json={"comment": "Start iron"})
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["status"] == "reviewed"
    assert reviewed.json()["reviewed_by_name"] == doctor.name

    # A late result reopens the order for review.
    late = results(tech, oid, [{"item_id": fbc, "analyte": "Ferritin", "value": "8",
                                "unit": "ug/L", "flag": "low"}])  # fmt: skip
    assert late.json()["status"] == "completed"
    assert late.json()["reviewed_at"] is None
    doctor.post(f"/api/v1/lab-orders/{oid}/review", json={})

    # Correcting a result: marked in error (kept), never edited; order needs review again.
    wrong = late.json()["items"][0]["results"][0]["id"]
    corrected = tech.post(
        f"/api/v1/lab-results/{wrong}/entered-in-error", json={"reason": "Wrong patient sample"}
    )
    assert corrected.status_code == 200, corrected.text
    body = corrected.json()
    assert body["status"] == "completed"
    kept = next(r for r in body["items"][0]["results"] if r["id"] == wrong)
    assert kept["status"] == "entered_in_error" and kept["value"] == "10.2"

    history = [(e["from_status"], e["to_status"]) for e in body["events"]]
    assert history[:4] == [
        (None, "requested"),
        ("requested", "collected"),
        ("collected", "sent"),
        ("sent", "completed"),
    ]
    assert history.count(("reviewed", "completed")) == 2


def test_state_machine(lab):
    tech, doctor = lab["technician"], lab["doctor"]
    oid = order(lab)["id"]
    detail = doctor.get(f"/api/v1/lab-orders/{oid}").json()
    item = detail["items"][0]["id"]
    # No results before a specimen exists; no completion without results.
    assert results(tech, oid, [{"item_id": item, "value": "1"}]).status_code == 409
    assert move(tech, oid, "completed").status_code == 409
    assert doctor.post(f"/api/v1/lab-orders/{oid}/review", json={}).status_code == 409
    # Collection may be skipped (patient went to the laboratory's depot).
    assert move(tech, oid, "sent").status_code == 200
    assert move(tech, oid, "collected").json()["error"]["code"] == "invalid_transition"
    assert move(tech, oid, "completed").json()["error"]["code"] == "no_results"
    results(tech, oid, [{"item_id": item, "value": "5.4"}])
    cancel = tech.post(f"/api/v1/lab-orders/{oid}/cancel", json={"reason": "Not needed"})
    assert cancel.json()["error"]["code"] == "has_results"

    # A result must belong to this order.
    other = order(lab)
    move(tech, other["id"], "collected")
    foreign = results(tech, other["id"], [{"item_id": item, "value": "1"}])
    assert foreign.status_code == 422

    # Cancellation needs a reason and is final.
    cancelled = doctor.post(
        f"/api/v1/lab-orders/{other['id']}/cancel", json={"reason": "Duplicate"}
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["cancel_reason"] == "Duplicate"
    assert move(tech, other["id"], "sent").status_code == 409


def test_ordering_rules(lab):
    doctor, owner = lab["doctor"], lab["owner"]
    eid = lab["encounter"]["id"]
    url = f"/api/v1/encounters/{eid}/lab-orders"
    assert doctor.post(url, json={"items": []}).status_code == 422
    assert doctor.post(url, json={"items": [{"specimen_type": "Blood"}]}).status_code == 422
    # Inactive tests and laboratories can't be ordered.
    hba1c = lab["tests"]["HBA1C"]
    owner.put(f"/api/v1/laboratory-tests/{hba1c['id']}", json={**hba1c, "is_active": False})
    assert doctor.post(url, json={"items": [{"test_id": hba1c["id"]}]}).status_code == 422
    # Renaming a test later does not change past orders (snapshot).
    created = order(lab)
    fbc = lab["tests"]["FBC"]
    owner.put(f"/api/v1/laboratory-tests/{fbc['id']}", json={**fbc, "name": "FBC renamed"})
    again = doctor.get(f"/api/v1/lab-orders/{created['id']}").json()
    assert again["items"][0]["test_name"] == "Full blood count"
    # Only open consultations take new orders.
    signed_note(doctor, eid)
    assert doctor.post(f"/api/v1/encounters/{eid}/close").status_code == 200
    closed = doctor.post(url, json={"items": [{"test_name": "Lipogram"}]})
    assert closed.json()["error"]["code"] == "encounter_closed"
    # Duplicate codes are rejected.
    dup = owner.post("/api/v1/laboratory-tests", json={"code": "FBC", "name": "Again"})
    assert dup.status_code == 409


def test_permissions(lab, add_member):
    owner, doctor, tech, rec = lab["owner"], lab["doctor"], lab["technician"], lab["receptionist"]
    oid = order(lab)["id"]
    eid = lab["encounter"]["id"]
    # Lab results are clinical: receptionists, owners, billing and auditors can't see them.
    for actor in (rec, owner, add_member(owner, "billing_officer"), add_member(owner, "auditor")):
        assert actor.get(f"/api/v1/lab-orders/{oid}").status_code == 403
        assert actor.get("/api/v1/lab-orders").status_code == 403
    # An unverified technician has no access (credentials before clinical access).
    unverified = add_member(owner, "lab_technician")
    assert unverified.get(f"/api/v1/lab-orders/{oid}").status_code == 403
    # Technicians process orders but can't order, review or read consultation notes.
    assert tech.get(f"/api/v1/lab-orders/{oid}").status_code == 200
    assert tech.get(f"/api/v1/encounters/{eid}").status_code == 403
    denied = tech.post(
        f"/api/v1/encounters/{eid}/lab-orders", json={"items": [{"test_name": "Lipogram"}]}
    )
    assert denied.status_code == 403
    move(tech, oid, "collected")
    detail = tech.get(f"/api/v1/lab-orders/{oid}").json()
    results(tech, oid, [{"item_id": detail["items"][0]["id"], "value": "5"}])
    move(tech, oid, "completed")
    assert tech.post(f"/api/v1/lab-orders/{oid}/review", json={}).status_code == 403
    # Configuration is administrative, not clinical.
    assert (
        doctor.post("/api/v1/laboratory-tests", json={"code": "X", "name": "Xx"}).status_code == 403
    )
    assert rec.get("/api/v1/laboratory-tests").status_code == 403
    assert doctor.get("/api/v1/laboratory-tests").status_code == 200
    assert owner.get("/api/v1/laboratories").status_code == 200


def test_branch_scope_and_cross_tenant(lab, add_member, new_actor):
    owner = lab["owner"]
    oid = order(lab)["id"]
    branch = owner.post("/api/v1/branches", json={"name": "Walvis Bay", "branch_code": "WVB"})
    elsewhere = add_member(owner, "practitioner", branch_id=branch.json()["id"])
    verify_practitioner(owner, elsewhere)
    assert elsewhere.get(f"/api/v1/lab-orders/{oid}").status_code == 403
    listed = elsewhere.get("/api/v1/lab-orders", params={"group": "all"}).json()
    assert listed["items"] == []

    other_owner = new_actor()
    other_owner.org_id = other_owner.post("/api/v1/organisations", json={"name": "Else"}).json()[
        "id"
    ]
    other_doctor = add_member(other_owner, "practitioner")
    verify_practitioner(other_owner, other_doctor)
    assert other_doctor.get(f"/api/v1/lab-orders/{oid}").status_code == 404
    assert other_doctor.get("/api/v1/lab-orders", params={"group": "all"}).json()["total"] == 0
    tech = add_member(other_owner, "lab_technician")
    verify_practitioner(other_owner, tech)
    assert move(tech, oid, "collected").status_code == 404


def test_database_integrity(lab, app_db):
    tech = lab["technician"]
    created = order(lab)
    oid = created["id"]
    move(tech, oid, "collected")
    recorded = results(tech, oid, [{"item_id": created["items"][0]["id"], "value": "5"}]).json()
    result_id = recorded["items"][0]["results"][0]["id"]
    statements = [
        ("UPDATE laboratory_results SET value = '6' WHERE id = %s", result_id),
        ("DELETE FROM laboratory_results WHERE id = %s", result_id),
        ("UPDATE laboratory_order_items SET test_name = 'x' WHERE order_id = %s", oid),
        ("DELETE FROM laboratory_order_events WHERE order_id = %s", oid),
        ("UPDATE laboratory_orders SET patient_id = gen_random_uuid() WHERE id = %s", oid),
        ("DELETE FROM laboratory_orders WHERE id = %s", oid),
    ]
    for sql, arg in statements:
        with app_db.transaction():
            app_db.execute("SELECT set_config('app.organisation_id', %s, true)", (tech.org_id,))
            with pytest.raises(
                (psycopg.errors.RaiseException, psycopg.errors.InsufficientPrivilege)
            ):
                app_db.execute(sql, (arg,))


def test_audit_has_no_clinical_content(lab):
    tech, owner = lab["technician"], lab["owner"]
    created = order(lab)
    move(tech, created["id"], "collected")
    results(tech, created["id"], [{**FBC[0], "item_id": created["items"][0]["id"]}])
    tech.get(f"/api/v1/lab-orders/{created['id']}")
    entries = owner.get("/api/v1/audit-logs", params={"limit": 200}).json()["items"]
    text = str([e["details"] for e in entries])
    for secret in ("Full blood count", "Haemoglobin", "10.2", "Tiredness", "Urine"):
        assert secret not in text
    actions = {e["action"] for e in entries}
    assert {"lab_order.created", "lab_order.status_changed", "lab_result.recorded"} <= actions
    views = [e for e in entries if e["action"] == "clinical_record.viewed"]
    assert any(v["details"].get("view") == "lab_order" for v in views)
