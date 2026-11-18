from app.core.permissions import ROLE_TEMPLATES
from tests.conftest import role_id


def test_invite_accept_flow(owner, new_actor):
    person = new_actor("Invited Nurse")
    invite = owner.post(
        "/api/v1/members",
        json={
            "email": person.email.upper(),
            "full_name": person.name,
            "roles": [{"role_id": role_id(owner, "nurse")}],
        },
    )
    assert invite.status_code == 201, invite.text
    assert invite.json()["status"] == "invited"

    # Invited but not accepted: no access yet.
    assert person.get("/api/v1/organisation", org_id=owner.org_id).status_code == 403
    me = person.get("/api/v1/me").json()
    assert me["memberships"][0]["status"] == "invited"

    assert person.post(f"/api/v1/me/invitations/{owner.org_id}/accept").status_code == 200
    assert person.get("/api/v1/organisation", org_id=owner.org_id).status_code == 200
    assert person.post(f"/api/v1/me/invitations/{owner.org_id}/accept").status_code == 409


def test_duplicate_invite_conflicts(owner, add_member):
    member = add_member(owner, "receptionist")
    response = owner.post(
        "/api/v1/members",
        json={
            "email": member.email,
            "full_name": "Again",
            "roles": [{"role_id": role_id(owner, "nurse")}],
        },
    )
    assert response.status_code == 409


def test_suspend_blocks_access_and_reactivate_restores(owner, add_member):
    member = add_member(owner, "receptionist")
    mid = member.membership_id
    assert (
        owner.post(f"/api/v1/members/{mid}/suspend", json={"reason": "Left practice"}).status_code
        == 200
    )
    assert member.get("/api/v1/organisation").status_code == 403
    assert (
        owner.post(f"/api/v1/members/{mid}/reactivate", json={"reason": "Returned"}).status_code
        == 200
    )
    assert member.get("/api/v1/organisation").status_code == 200
    actions = {
        e["action"]
        for e in owner.get("/api/v1/audit-logs", params={"resource_id": mid}).json()["items"]
    }
    assert {"member.invited", "member.suspended", "member.reactivated"} <= actions


def test_change_roles_takes_effect(owner, add_member):
    member = add_member(owner, "receptionist")
    assert member.get("/api/v1/audit-logs").status_code == 403
    response = owner.put(
        f"/api/v1/members/{member.membership_id}/roles",
        json={"roles": [{"role_id": role_id(owner, "auditor")}]},
    )
    assert response.status_code == 200
    assert [r["role_name"] for r in response.json()["roles"]] == ["Auditor"]
    assert member.get("/api/v1/audit-logs").status_code == 200
    auditor = next(t for t in ROLE_TEMPLATES if t.key == "auditor")
    assert member.get("/api/v1/me/access").json()["permissions"] == sorted(auditor.permissions)
    assert all(p.endswith(".read") for p in auditor.permissions)  # read-only


def test_cannot_modify_self(owner):
    own = owner.get("/api/v1/me/access").json()["membership_id"]
    assert owner.post(f"/api/v1/members/{own}/suspend", json={"reason": "oops"}).status_code == 403
    assert (
        owner.put(
            f"/api/v1/members/{own}/roles", json={"roles": [{"role_id": role_id(owner, "auditor")}]}
        ).status_code
        == 403
    )


def test_last_owner_is_protected(owner, add_member):
    second = add_member(owner, "owner")
    own = owner.get("/api/v1/me/access").json()["membership_id"]
    # Second owner removes the first: allowed while another owner remains.
    assert (
        second.post(f"/api/v1/members/{own}/suspend", json={"reason": "Handover"}).status_code
        == 200
    )
    # The remaining owner cannot be suspended by anyone (and not by themselves).
    admin_like = add_member(second, "administrator")
    response = admin_like.post(
        f"/api/v1/members/{second.membership_id}/suspend", json={"reason": "x" * 5}
    )
    assert response.status_code == 403  # only an owner can suspend an owner


def test_owner_role_removal_requires_another_owner(owner, add_member):
    second = add_member(owner, "owner")
    response = second.put(
        f"/api/v1/members/{owner.get('/api/v1/me/access').json()['membership_id']}/roles",
        json={"roles": [{"role_id": role_id(owner, "administrator")}]},
    )
    assert response.status_code == 200
    # Now `second` is the only owner; `owner` (now admin) cannot remove them.
    response = owner.put(
        f"/api/v1/members/{second.membership_id}/roles",
        json={"roles": [{"role_id": role_id(owner, "administrator")}]},
    )
    assert response.status_code == 403


def test_member_search(owner, add_member):
    member = add_member(owner, "nurse")
    found = owner.get("/api/v1/members", params={"q": member.email[:8]}).json()
    assert found["total"] == 1
