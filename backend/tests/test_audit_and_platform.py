import psycopg
import pytest


def test_audit_log_is_append_only_for_app(owner, app_db):
    with app_db.transaction():
        app_db.execute("SELECT set_config('app.organisation_id', %s, true)", (owner.org_id,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            app_db.execute("UPDATE audit_logs SET action = 'tampered'")


def test_audit_log_is_append_only_for_owner(owner, owner_db):
    with owner_db.transaction():
        owner_db.execute("SELECT set_config('app.organisation_id', %s, true)", (owner.org_id,))
        with pytest.raises(psycopg.errors.RaiseException):
            owner_db.execute("DELETE FROM audit_logs")
    with pytest.raises(psycopg.errors.RaiseException):
        owner_db.execute("TRUNCATE audit_logs")


def test_non_admin_cannot_use_platform_endpoints(owner):
    assert owner.get("/api/v1/platform/organisations").status_code == 403


def test_platform_admin_manages_tenants_without_tenant_data(owner, new_actor, owner_db):
    admin = new_actor("Platform Admin")
    admin.get("/api/v1/me")
    owner_db.execute("UPDATE users SET is_platform_admin = true WHERE email = %s", (admin.email,))

    listed = admin.get(
        "/api/v1/platform/organisations",
        params={"q": owner.get("/api/v1/organisation").json()["name"]},
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    # Platform admin is not a member: no access to the tenant's own data.
    assert admin.get("/api/v1/branches", org_id=owner.org_id).status_code == 403
    assert admin.get("/api/v1/members", org_id=owner.org_id).status_code == 403

    suspended = admin.patch(
        f"/api/v1/platform/organisations/{owner.org_id}",
        json={"status": "suspended", "reason": "Unpaid subscription"},
    )
    assert suspended.status_code == 200
    blocked = owner.get("/api/v1/organisation")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "organisation_suspended"

    admin.patch(
        f"/api/v1/platform/organisations/{owner.org_id}",
        json={"status": "active", "reason": "Paid"},
    )
    logs = owner.get(
        "/api/v1/audit-logs", params={"action": "platform.organisation_status_changed"}
    ).json()
    assert logs["total"] == 2


def test_mfa_required_for_privileged_actions(owner, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "oidc_mfa_acr_values", ["mfa"])
    response = owner.client.get("/api/v1/audit-logs", headers=owner.headers(acr="1"))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "mfa_required"
    assert (
        owner.client.get("/api/v1/audit-logs", headers=owner.headers(acr="mfa")).status_code == 200
    )
    # Non-privileged reads are unaffected.
    assert owner.client.get("/api/v1/branches", headers=owner.headers(acr="1")).status_code == 200
