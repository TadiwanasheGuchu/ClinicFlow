from tests.conftest import main_branch_id, role_id


def test_registration_creates_owner_roles_and_branch(owner):
    org = owner.get("/api/v1/organisation").json()
    assert org["currency"] == "NAD"
    assert org["timezone"] == "Africa/Windhoek"
    assert org["settings"]["patient_number_prefix"] == "P"

    roles = owner.get("/api/v1/roles").json()
    keys = {r["template_key"] for r in roles}
    assert {"owner", "administrator", "receptionist", "practitioner", "auditor"} <= keys
    owner_role = next(r for r in roles if r["template_key"] == "owner")
    assert owner_role["is_system"] is True
    # Running a practice does not grant clinical access.
    assert "clinical.read" not in owner_role["permissions"]

    branches = owner.get("/api/v1/branches").json()
    assert branches["total"] == 1
    assert branches["items"][0]["branch_code"] == "MAIN"

    me = owner.get("/api/v1/me").json()
    assert me["memberships"][0]["status"] == "active"
    access = owner.get("/api/v1/me/access").json()
    assert access["is_owner"] is True


def test_registration_is_audited(owner):
    logs = owner.get("/api/v1/audit-logs", params={"action": "organisation.registered"}).json()
    assert logs["total"] == 1
    entry = logs["items"][0]
    assert entry["resource_id"] == owner.org_id
    assert entry["request_id"]


def test_update_organisation_and_settings(owner):
    response = owner.patch(
        "/api/v1/organisation",
        json={"phone": "+264 64 123 456", "settings": {"booking_buffer_minutes": 10}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["phone"] == "+264 64 123 456"
    assert body["settings"]["booking_buffer_minutes"] == 10
    assert body["settings"]["patient_number_prefix"] == "P"  # untouched

    logs = owner.get("/api/v1/audit-logs", params={"action": "organisation.updated"}).json()
    assert logs["total"] == 1


def test_update_rejects_invalid_values(owner):
    assert owner.patch("/api/v1/organisation", json={"timezone": "Mars/Base"}).status_code == 422
    assert owner.patch("/api/v1/organisation", json={"name": None}).status_code == 422
    assert (
        owner.patch(
            "/api/v1/organisation", json={"settings": {"patient_number_prefix": "p1"}}
        ).status_code
        == 422
    )


def test_tenant_header_required(owner):
    response = owner.client.get(
        "/api/v1/organisation", headers={"Authorization": owner.headers()["Authorization"]}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "organisation_required"


def test_helpers_resolve(owner):
    assert role_id(owner, "receptionist")
    assert main_branch_id(owner)
