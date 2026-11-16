import uuid

from tests.conftest import make_patient


def test_register_assigns_sequential_numbers_and_audits(owner):
    first = make_patient(owner)
    second = make_patient(owner)
    assert first["patient_number"] == "P-000001"
    assert second["patient_number"] == "P-000002"
    logs = owner.get("/api/v1/audit-logs", params={"action": "patient.registered"}).json()
    assert logs["total"] == 2
    # Personal details are not copied into the audit log.
    assert "first_name" not in str(logs["items"][0]["details"])


def test_viewing_a_patient_is_audited(owner):
    patient = make_patient(owner)
    assert owner.get(f"/api/v1/patients/{patient['id']}").status_code == 200
    logs = owner.get(
        "/api/v1/audit-logs", params={"action": "patient.viewed", "resource_id": patient["id"]}
    ).json()
    assert logs["total"] == 1


def test_duplicate_detection(owner):
    original = make_patient(owner, first="Ndapewa", last="Shikongo", phone="+264 81 123 4567")
    attempt = owner.post(
        "/api/v1/patients",
        json={
            "first_name": "Ndapewa",
            "last_name": "Shikongo",
            "date_of_birth": "1990-04-12",
        },
    )
    assert attempt.status_code == 409
    error = attempt.json()["error"]
    assert error["code"] == "possible_duplicate"
    assert [c["id"] for c in error["details"]["candidates"]] == [original["id"]]

    # Same DOB and phone, different spelling of the name, is still flagged.
    attempt = owner.post(
        "/api/v1/patients",
        json={
            "first_name": "Ndapeua",
            "last_name": "Shikongo-Amutenya",
            "date_of_birth": "1990-04-12",
            "phone": "+264811234567",
        },
    )
    assert attempt.status_code == 409

    confirmed = owner.post(
        "/api/v1/patients",
        json={
            "first_name": "Ndapewa",
            "last_name": "Shikongo",
            "date_of_birth": "1990-04-12",
            "confirm_not_duplicate": True,
        },
    )
    assert confirmed.status_code == 201
    logs = owner.get("/api/v1/audit-logs", params={"action": "patient.registered"}).json()
    assert any(e["details"]["confirmed_not_duplicate"] for e in logs["items"])


def test_search(owner):
    target = make_patient(
        owner, first="Tuyeni", last="Haufiku", date_of_birth="1985-01-30", phone="+264 81 555 0101"
    )
    make_patient(owner, first="Other", last="Person")

    def ids(q):
        return [p["id"] for p in owner.get("/api/v1/patients", params={"q": q}).json()["items"]]

    assert ids("tuy hauf") == [target["id"]]
    assert ids("Haufiku") == [target["id"]]
    assert ids(target["patient_number"].lower()) == [target["id"]]
    assert ids("30/01/1985") == [target["id"]]
    assert ids("81 555 0101") == [target["id"]]
    assert ids("nobody-matches") == []


def test_update_records_fields_not_values(owner):
    patient = make_patient(owner)
    response = owner.patch(
        f"/api/v1/patients/{patient['id']}",
        json={
            "phone": "+264 81 000 0000",
            "emergency_contact": {
                "name": "Maria Test",
                "phone": "+264 81 999 9999",
                "relationship": "Sister",
            },
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["emergency_contact"]["name"] == "Maria Test"
    log = owner.get("/api/v1/audit-logs", params={"action": "patient.updated"}).json()["items"][0]
    assert log["details"] == {"fields": ["emergency_contact", "phone"]}
    assert (
        owner.patch(f"/api/v1/patients/{patient['id']}", json={"last_name": None}).status_code
        == 422
    )


def test_validation(owner):
    future = owner.post(
        "/api/v1/patients",
        json={
            "first_name": "A",
            "last_name": "B",
            "date_of_birth": "2999-01-01",
        },
    )
    assert future.status_code == 422


def test_permissions(owner, add_member):
    receptionist = add_member(owner, "receptionist")
    auditor = add_member(owner, "auditor")
    patient = make_patient(receptionist)
    assert auditor.get("/api/v1/patients").status_code == 403
    assert auditor.get(f"/api/v1/patients/{patient['id']}").status_code == 403


def test_cross_tenant_patients_invisible(owner, new_actor):
    patient = make_patient(owner)
    other = new_actor()
    other.org_id = other.post("/api/v1/organisations", json={"name": "Elsewhere"}).json()["id"]
    assert other.get(f"/api/v1/patients/{patient['id']}").status_code == 404
    assert other.patch(
        f"/api/v1/patients/{patient['id']}", json={"phone": "+264 81 1"}
    ).status_code in (404, 422)
    assert other.get("/api/v1/patients").json()["total"] == 0
    assert other.get(f"/api/v1/patients/{uuid.uuid4()}").status_code == 404
    # Numbering is per organisation.
    assert make_patient(other)["patient_number"] == "P-000001"
