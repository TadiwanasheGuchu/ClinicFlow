"""Acceptance (Phase 1): two independent organisations; their data stays isolated."""

import uuid

import psycopg
import pytest

from tests.conftest import main_branch_id, role_id


@pytest.fixture
def two_orgs(owner, new_actor):
    other = new_actor("Other Owner")
    response = other.post("/api/v1/organisations", json={"name": "Other Clinic"})
    assert response.status_code == 201
    other.org_id = response.json()["id"]
    return owner, other


def test_cannot_select_another_organisation(two_orgs):
    a, b = two_orgs
    for path in ("/api/v1/organisation", "/api/v1/branches", "/api/v1/members", "/api/v1/roles"):
        response = b.get(path, org_id=a.org_id)
        assert response.status_code == 403, path
        assert response.json()["error"]["code"] == "no_tenant_access"


def test_unknown_organisation_gives_same_answer(new_actor):
    actor = new_actor()
    response = actor.get("/api/v1/organisation", org_id=str(uuid.uuid4()))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "no_tenant_access"


def test_cross_tenant_ids_are_not_found(two_orgs):
    a, b = two_orgs
    a_branch = main_branch_id(a)
    a_role = role_id(a, "receptionist")
    a_member = a.get("/api/v1/members").json()["items"][0]["id"]

    # B uses its own (valid) tenant but A's resource ids.
    assert b.get(f"/api/v1/branches/{a_branch}").status_code == 404
    assert b.patch(f"/api/v1/branches/{a_branch}", json={"name": "Hijacked"}).status_code == 404
    assert b.get(f"/api/v1/roles/{a_role}").status_code == 404
    assert b.get(f"/api/v1/members/{a_member}").status_code == 404
    assert (
        b.post(f"/api/v1/members/{a_member}/suspend", json={"reason": "x" * 5}).status_code == 404
    )


def test_cannot_assign_another_tenants_role_or_branch(two_orgs, new_actor):
    a, b = two_orgs
    person = new_actor()
    payload = {
        "email": person.email,
        "full_name": "Cross Tenant",
        "roles": [{"role_id": role_id(a, "receptionist")}],
    }
    assert b.post("/api/v1/members", json=payload).status_code == 422

    payload["roles"] = [{"role_id": role_id(b, "receptionist"), "branch_id": main_branch_id(a)}]
    assert b.post("/api/v1/members", json=payload).status_code == 422


def test_lists_only_show_own_tenant(two_orgs):
    a, b = two_orgs
    a_ids = {x["id"] for x in a.get("/api/v1/branches").json()["items"]}
    b_ids = {x["id"] for x in b.get("/api/v1/branches").json()["items"]}
    assert a_ids.isdisjoint(b_ids)
    b_logs = b.get("/api/v1/audit-logs").json()["items"]
    assert all(entry["resource_id"] != a.org_id for entry in b_logs)


def test_me_lists_only_own_memberships(two_orgs):
    a, b = two_orgs
    orgs = {m["organisation_id"] for m in b.get("/api/v1/me").json()["memberships"]}
    assert orgs == {b.org_id}


# --- Database-level defence in depth (Row-Level Security) ---------------------


def test_rls_hides_all_tenant_rows_without_scope(two_orgs, app_db):
    for table in (
        "organisations",
        "branches",
        "roles",
        "role_permissions",
        "organisation_memberships",
        "membership_roles",
        "audit_logs",
    ):
        count = app_db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        assert count == 0, table


def test_rls_scopes_to_current_organisation(two_orgs, app_db):
    a, b = two_orgs
    with app_db.transaction():
        app_db.execute("SELECT set_config('app.organisation_id', %s, true)", (a.org_id,))
        orgs = {str(r[0]) for r in app_db.execute("SELECT DISTINCT organisation_id FROM branches")}
    assert orgs == {a.org_id}


def test_rls_blocks_writes_into_another_tenant(two_orgs, app_db):
    a, b = two_orgs
    with pytest.raises(psycopg.errors.InsufficientPrivilege), app_db.transaction():
        app_db.execute("SELECT set_config('app.organisation_id', %s, true)", (a.org_id,))
        app_db.execute(
            "INSERT INTO branches (id, organisation_id, name, branch_code, operating_hours, "
            "is_active) VALUES (gen_random_uuid(), %s, 'Injected', 'INJ', '{}', true)",
            (b.org_id,),
        )


def test_rls_applies_to_schema_owner(two_orgs, owner_db):
    # FORCE ROW LEVEL SECURITY: even the table owner sees nothing without a scope.
    assert owner_db.execute("SELECT count(*) FROM branches").fetchone()[0] == 0


def test_app_role_cannot_bypass_rls(app_db):
    row = app_db.execute(
        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
    ).fetchone()
    assert row == (False, False)
