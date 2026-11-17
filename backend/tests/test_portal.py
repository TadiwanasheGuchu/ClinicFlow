"""Acceptance (Phase 3): patients book without reception; duplicates prevented; access is
limited to the patient's own record."""

import uuid

from tests.conftest import book, local_time, make_patient, portal_book


def test_public_info_only_when_enabled(clinic, client):
    slug = clinic["owner"].get("/api/v1/organisation").json()["slug"]
    assert client.get(f"/api/v1/portal/{slug}").status_code == 404
    assert client.get("/api/v1/portal/no-such-practice").status_code == 404


def test_public_info(portal, client):
    info = client.get(portal["base"]).json()
    assert [p["id"] for p in info["providers"]] == [portal["provider_id"]]
    assert [t["id"] for t in info["appointment_types"]] == [portal["type_id"]]
    assert info["policy"]["min_notice_hours"] == 2


def test_self_registration(portal, patient_user):
    me = patient_user.get(f"{portal['base']}/me").json()
    assert me["linked"] is True
    assert me["patient"]["patient_number"].startswith("P-")
    assert me["patient"]["email"] == patient_user.email
    again = patient_user.post(
        f"{portal['base']}/register",
        json={
            "first_name": "X",
            "last_name": "Y",
            "date_of_birth": "1990-01-01",
            "phone": "+264 81 1111111",
        },
    )
    assert again.status_code == 409
    logs = (
        portal["owner"].get("/api/v1/audit-logs", params={"action": "portal.account_linked"}).json()
    )
    assert logs["items"][0]["details"] == {"via": "patient_portal", "method": "registration"}


def test_self_registration_never_reveals_existing_records(portal, new_actor):
    make_patient(portal["owner"], first="Ndapewa", last="Existing", date_of_birth="1980-02-02")
    stranger = new_actor()
    response = stranger.post(
        f"{portal['base']}/register",
        json={
            "first_name": "Ndapewa",
            "last_name": "Existing",
            "date_of_birth": "1980-02-02",
            "phone": "+264 81 000 1111",
        },
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "record_may_exist"
    assert "details" not in error  # no candidate names, numbers or phones


def test_link_with_code(portal, new_actor):
    owner = portal["owner"]
    patient = make_patient(owner, date_of_birth="1975-05-05")
    code = owner.post(f"/api/v1/patients/{patient['id']}/portal-link-code").json()["code"]
    person = new_actor()
    wrong = person.post(
        f"{portal['base']}/link", json={"code": code, "date_of_birth": "1975-05-06"}
    )
    assert wrong.status_code == 422
    ok = person.post(
        f"{portal['base']}/link", json={"code": code.lower(), "date_of_birth": "1975-05-05"}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["patient"]["patient_number"] == patient["patient_number"]
    # Single use: another account cannot reuse it.
    other = new_actor()
    assert (
        other.post(
            f"{portal['base']}/link", json={"code": code, "date_of_birth": "1975-05-05"}
        ).status_code
        == 422
    )
    status = owner.get(f"/api/v1/patients/{patient['id']}/portal-account").json()
    assert status["linked"] is True and status["email"] == person.email


def test_new_code_replaces_old_and_attempts_are_limited(portal, new_actor):
    owner = portal["owner"]
    patient = make_patient(owner, date_of_birth="1970-01-01")
    first = owner.post(f"/api/v1/patients/{patient['id']}/portal-link-code").json()["code"]
    owner.post(f"/api/v1/patients/{patient['id']}/portal-link-code")
    person = new_actor()
    assert (
        person.post(
            f"{portal['base']}/link", json={"code": first, "date_of_birth": "1970-01-01"}
        ).status_code
        == 422
    )
    for _ in range(4):
        person.post(
            f"{portal['base']}/link", json={"code": "AAAA-AAAA", "date_of_birth": "1970-01-01"}
        )
    assert (
        person.post(
            f"{portal['base']}/link", json={"code": "AAAA-AAAA", "date_of_birth": "1970-01-01"}
        ).status_code
        == 429
    )


def test_unlinked_users_cannot_book_or_see_slots(portal, new_actor):
    person = new_actor()
    response = portal_book(person, portal, local_time(3, "09:00"))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_linked"


def test_patient_books_online(portal, patient_user):
    slots = patient_user.get(
        f"{portal['base']}/slots",
        params={
            "provider_id": portal["provider_id"],
            "branch_id": portal["branch_id"],
            "appointment_type_id": portal["type_id"],
            "date": local_time(3, "00:00")[:10],
        },
    ).json()
    assert slots
    response = portal_book(patient_user, portal, slots[0]["start_at"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "confirmed"
    staff_view = portal["receptionist"].get(f"/api/v1/appointments/{body['id']}").json()
    assert staff_view["booking_source"] == "online"
    # The slot is now taken for everyone, online or at reception.
    assert (
        book(
            portal["receptionist"],
            portal,
            make_patient(portal["receptionist"])["id"],
            slots[0]["start_at"],
        ).status_code
        == 422
    )
    listed = patient_user.get(f"{portal['base']}/appointments").json()
    assert [a["id"] for a in listed] == [body["id"]]


def test_online_rules(portal, patient_user, add_member):
    from datetime import UTC, datetime, timedelta

    soon = (datetime.now(UTC) + timedelta(minutes=30)).isoformat()
    assert portal_book(patient_user, portal, soon).json()["error"]["code"] == "too_soon"
    far = local_time(90, "09:00")
    assert portal_book(patient_user, portal, far).json()["error"]["code"] == "too_far"
    # Practitioner not offered online.
    portal["owner"].patch(
        f"/api/v1/providers/{portal['provider_id']}", json={"online_booking_enabled": False}
    )
    assert portal_book(patient_user, portal, local_time(3, "09:00")).status_code == 404


def test_upcoming_limit(portal, patient_user):
    for i, hhmm in enumerate(["09:00", "10:00", "11:00"]):
        assert portal_book(patient_user, portal, local_time(3 + i, hhmm)).status_code == 201
    response = portal_book(patient_user, portal, local_time(7, "09:00"))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "too_many_upcoming"


def test_patients_cannot_reach_each_others_appointments(portal, patient_user, new_actor):
    appt = portal_book(patient_user, portal, local_time(4, "09:00")).json()
    other = new_actor()
    other.post(
        f"{portal['base']}/register",
        json={
            "first_name": "Other",
            "last_name": f"P{uuid.uuid4().hex[:6]}",
            "date_of_birth": "1999-09-09",
            "phone": "+264 81 999 0000",
        },
    )
    assert other.get(f"{portal['base']}/appointments/{appt['id']}").status_code == 404
    assert (
        other.post(f"{portal['base']}/appointments/{appt['id']}/cancel", json={}).status_code == 404
    )
    assert other.get(f"{portal['base']}/appointments").json() == []


def test_account_is_per_practice(portal, patient_user, new_actor):
    other_owner = new_actor()
    org = other_owner.post("/api/v1/organisations", json={"name": "Another Practice"}).json()
    other_owner.org_id = org["id"]
    other_owner.patch("/api/v1/organisation", json={"settings": {"portal_enabled": True}})
    me = patient_user.get(f"/api/v1/portal/{org['slug']}/me").json()
    assert me["linked"] is False


def test_cancel_and_reschedule_respect_cutoff(portal, patient_user):
    portal["owner"].patch(
        "/api/v1/organisation", json={"settings": {"online_cancel_cutoff_hours": 72}}
    )
    near = portal_book(patient_user, portal, local_time(2, "16:00"))
    assert near.status_code == 201, near.text
    assert near.json()["can_change"] is False  # inside the 72-hour cut-off
    response = patient_user.post(
        f"{portal['base']}/appointments/{near.json()['id']}/cancel", json={}
    )
    assert response.json()["error"]["code"] == "change_window_closed"
    far = portal_book(patient_user, portal, local_time(5, "09:00")).json()
    moved = patient_user.post(
        f"{portal['base']}/appointments/{far['id']}/reschedule",
        json={"start_at": local_time(5, "11:00")},
    )
    assert moved.status_code == 200, moved.text
    from datetime import datetime

    assert datetime.fromisoformat(moved.json()["start_at"]) == datetime.fromisoformat(
        local_time(5, "11:00")
    )
    cancelled = patient_user.post(
        f"{portal['base']}/appointments/{far['id']}/cancel", json={"reason": "Feeling better"}
    )
    assert cancelled.json()["status"] == "cancelled"
    history = portal["owner"].get(f"/api/v1/appointments/{far['id']}").json()["events"]
    assert [e["event_type"] for e in history] == ["created", "rescheduled", "cancelled"]


def test_requests_when_auto_confirm_off(portal, patient_user):
    portal["owner"].patch("/api/v1/organisation", json={"settings": {"online_auto_confirm": False}})
    response = portal_book(patient_user, portal, local_time(3, "14:00"))
    assert response.json()["status"] == "requested"


def test_revoked_access(portal, patient_user):
    me = patient_user.get(f"{portal['base']}/me").json()
    patients = (
        portal["owner"]
        .get("/api/v1/patients", params={"q": me["patient"]["patient_number"]})
        .json()
    )
    pid = patients["items"][0]["id"]
    assert portal["owner"].post(f"/api/v1/patients/{pid}/portal-account/revoke").status_code == 200
    assert patient_user.get(f"{portal['base']}/appointments").status_code == 403
    again = patient_user.post(
        f"{portal['base']}/register",
        json={
            "first_name": "New",
            "last_name": "Identity",
            "date_of_birth": "2000-01-01",
            "phone": "+264 81 123 0000",
        },
    )
    assert again.json()["error"]["code"] == "account_revoked"


def test_portal_address(portal):
    owner = portal["owner"]
    assert owner.patch("/api/v1/organisation", json={"slug": "admin"}).status_code == 409
    response = owner.patch("/api/v1/organisation", json={"slug": f"erongo-{uuid.uuid4().hex[:6]}"})
    assert response.status_code == 200
    assert owner.patch("/api/v1/organisation", json={"slug": "Bad Slug"}).status_code == 422
