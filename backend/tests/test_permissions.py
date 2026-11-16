"""Acceptance (Phase 1): permissions are enforced by the backend."""

from tests.conftest import main_branch_id, role_id


def test_receptionist_cannot_administer(owner, add_member):
    receptionist = add_member(owner, "receptionist")
    assert receptionist.get("/api/v1/branches").status_code == 200
    assert (
        receptionist.post(
            "/api/v1/branches", json={"name": "Walvis Bay", "branch_code": "WVB"}
        ).status_code
        == 403
    )
    assert receptionist.patch("/api/v1/organisation", json={"name": "X Clinic"}).status_code == 403
    assert receptionist.get("/api/v1/members").status_code == 403
    assert receptionist.get("/api/v1/roles").status_code == 403
    assert receptionist.get("/api/v1/audit-logs").status_code == 403


def test_denied_attempts_are_audited(owner, add_member):
    receptionist = add_member(owner, "receptionist")
    receptionist.get("/api/v1/audit-logs")
    logs = owner.get("/api/v1/audit-logs", params={"action": "access.denied"}).json()["items"]
    assert any(e["details"].get("permission") == "audit.read" and e["actor_user_id"] for e in logs)


def test_auditor_is_read_only(owner, add_member):
    auditor = add_member(owner, "auditor")
    assert auditor.get("/api/v1/audit-logs").status_code == 200
    assert auditor.get("/api/v1/roles").status_code == 200
    assert auditor.post("/api/v1/roles", json={"name": "Sneaky"}).status_code == 403


def test_branch_scoped_manager(owner, add_member):
    main = main_branch_id(owner)
    other = owner.post("/api/v1/branches", json={"name": "Walvis Bay", "branch_code": "WVB"})
    assert other.status_code == 201
    manager = add_member(owner, "branch_manager", branch_id=main)

    assert (
        manager.patch(f"/api/v1/branches/{main}", json={"phone": "+264 64 000 111"}).status_code
        == 200
    )
    assert (
        manager.patch(
            f"/api/v1/branches/{other.json()['id']}", json={"phone": "+264 64 000 222"}
        ).status_code
        == 403
    )
    # Creating branches needs the permission organisation-wide.
    assert (
        manager.post(
            "/api/v1/branches", json={"name": "Hentiesbaai", "branch_code": "HTB"}
        ).status_code
        == 403
    )


def test_admin_cannot_grant_owner_role(owner, add_member, new_actor):
    admin = add_member(owner, "administrator")
    person = new_actor()
    response = admin.post(
        "/api/v1/members",
        json={
            "email": person.email,
            "full_name": "Would-be Owner",
            "roles": [{"role_id": role_id(owner, "owner")}],
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "owner_only"


def test_admin_cannot_grant_permissions_they_lack(owner, add_member, new_actor):
    admin = add_member(owner, "administrator")
    # Administrators hold no clinical permissions, so cannot hand them out.
    response = admin.post(
        "/api/v1/roles", json={"name": "Shadow doctor", "permissions": ["clinical.read"]}
    )
    assert response.status_code == 403
    person = new_actor()
    response = admin.post(
        "/api/v1/members",
        json={
            "email": person.email,
            "full_name": "Practitioner",
            "roles": [{"role_id": role_id(owner, "practitioner")}],
        },
    )
    assert response.status_code == 403
    # Nor widen an existing role with permissions they lack.
    reception = role_id(owner, "receptionist")
    current = owner.get(f"/api/v1/roles/{reception}").json()["permissions"]
    response = admin.patch(
        f"/api/v1/roles/{reception}", json={"permissions": [*current, "billing.manage"]}
    )
    assert response.status_code == 403


def test_owner_can_create_clinical_role(owner):
    response = owner.post(
        "/api/v1/roles",
        json={
            "name": "Dentist",
            "permissions": ["clinical.read", "clinical.write", "patients.read"],
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["permissions"] == ["clinical.read", "clinical.write", "patients.read"]


def test_system_role_is_locked(owner):
    owner_role = role_id(owner, "owner")
    assert owner.patch(f"/api/v1/roles/{owner_role}", json={"name": "Boss"}).status_code == 403
    assert owner.delete(f"/api/v1/roles/{owner_role}").status_code == 403


def test_role_crud_and_audit(owner):
    created = owner.post(
        "/api/v1/roles", json={"name": "Front desk lead", "permissions": ["patients.read"]}
    )
    assert created.status_code == 201
    rid = created.json()["id"]
    assert owner.post("/api/v1/roles", json={"name": "Front desk lead"}).status_code == 409
    updated = owner.patch(
        f"/api/v1/roles/{rid}", json={"permissions": ["patients.read", "appointments.read"]}
    )
    assert updated.json()["permissions"] == ["appointments.read", "patients.read"]
    assert owner.delete(f"/api/v1/roles/{rid}").status_code == 204
    actions = {
        e["action"]
        for e in owner.get("/api/v1/audit-logs", params={"resource_type": "role"}).json()["items"]
    }
    assert {"role.created", "role.updated", "role.deleted"} <= actions


def test_unknown_permission_rejected(owner):
    assert (
        owner.post("/api/v1/roles", json={"name": "Odd", "permissions": ["everything"]}).status_code
        == 422
    )


def test_assigned_role_cannot_be_deleted(owner, add_member):
    add_member(owner, "nurse")
    assert owner.delete(f"/api/v1/roles/{role_id(owner, 'nurse')}").status_code == 409
