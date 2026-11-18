"""Phase 6 — staff rostering. No overlapping shifts or leave (database-enforced); staff
request their own leave and someone else approves it; approved practitioner leave blocks
bookings; leave details stay private to the person and their managers."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from tests.conftest import TZ, book, local_time, make_patient, verify_practitioner


def monday(weeks_ahead: int = 1) -> date:
    today = date.today()
    return today - timedelta(days=today.weekday()) + timedelta(weeks=weeks_ahead)


def at(day: date, hhmm: str) -> str:
    return local_time((day - date.today()).days, hhmm)


def membership_id(actor) -> str:
    me = actor.get("/api/v1/me").json()
    return next(
        m["membership_id"] for m in me["memberships"] if m["organisation_id"] == actor.org_id
    )


def shift(actor, clinic, member, day, start="08:00", end="16:00", **extra):
    return actor.post(
        "/api/v1/shifts",
        json={
            "branch_id": clinic["branch_id"],
            "membership_id": member,
            "starts_at": at(day, start),
            "ends_at": at(day, end),
            "duty": "Reception",
            **extra,
        },
    )


def test_shifts_roster_and_copy_week(clinic):
    owner, rec = clinic["owner"], clinic["receptionist"]
    week = monday()
    created = shift(owner, clinic, rec.membership_id, week)
    assert created.status_code == 201, created.text
    overlap = shift(owner, clinic, rec.membership_id, week, "15:00", "20:00")
    assert overlap.json()["error"]["code"] == "shift_overlap"
    assert shift(owner, clinic, rec.membership_id, week, "16:00", "20:00").status_code == 201
    assert shift(owner, clinic, rec.membership_id, week + timedelta(days=2)).status_code == 201

    roster = owner.get(
        "/api/v1/roster", params={"branch_id": clinic["branch_id"], "start": week.isoformat()}
    ).json()
    assert len(roster["shifts"]) == 3
    assert roster["hours"][rec.membership_id] == 20.0
    assert rec.membership_id in {s["membership_id"] for s in roster["staff"]}

    copied = owner.post(
        "/api/v1/shifts/copy-week",
        json={
            "branch_id": clinic["branch_id"],
            "from_start": week.isoformat(),
            "to_start": (week + timedelta(days=7)).isoformat(),
        },
    ).json()
    assert copied == {"created": 3, "skipped": 0}
    again = owner.post(
        "/api/v1/shifts/copy-week",
        json={
            "branch_id": clinic["branch_id"],
            "from_start": week.isoformat(),
            "to_start": (week + timedelta(days=7)).isoformat(),
        },
    ).json()
    assert again == {"created": 0, "skipped": 3}
    nxt = owner.get(
        "/api/v1/roster",
        params={"branch_id": clinic["branch_id"], "start": (week + timedelta(days=7)).isoformat()},
    ).json()
    local = sorted(
        datetime.fromisoformat(s["starts_at"]).astimezone(ZoneInfo(TZ)).strftime("%H:%M")
        for s in nxt["shifts"]
    )
    assert local == ["08:00", "08:00", "16:00"]

    # Cancelling frees the time.
    sid = created.json()["id"]
    assert owner.post(f"/api/v1/shifts/{sid}/cancel").json()["status"] == "cancelled"
    assert shift(owner, clinic, rec.membership_id, week, "09:00", "12:00").status_code == 201

    # Staff see the roster and their own shifts, but can't plan it.
    assert (
        rec.get(
            "/api/v1/roster", params={"branch_id": clinic["branch_id"], "start": week.isoformat()}
        ).status_code
        == 200
    )
    mine = rec.get("/api/v1/me/roster", params={"start": week.isoformat()}).json()
    assert len(mine["shifts"]) == 6  # 3 left in week one, 3 copied into week two
    assert shift(rec, clinic, rec.membership_id, week + timedelta(days=4)).status_code == 403


def test_leave_requests_and_privacy(clinic, add_member):
    owner, rec = clinic["owner"], clinic["receptionist"]
    week = monday(2)
    shift(owner, clinic, rec.membership_id, week + timedelta(days=1))
    request = rec.post(
        "/api/v1/me/leave",
        json={
            "starts_on": week.isoformat(),
            "ends_on": (week + timedelta(days=2)).isoformat(),
            "leave_type": "sick",
            "reason": "Synthetic test reason",
        },
    )
    assert request.status_code == 201, request.text
    leave = request.json()
    assert leave["status"] == "requested" and leave["leave_type"] == "sick"
    dup = rec.post(
        "/api/v1/me/leave",
        json={
            "starts_on": (week + timedelta(days=1)).isoformat(),
            "ends_on": (week + timedelta(days=1)).isoformat(),
            "leave_type": "annual",
        },
    )
    assert dup.json()["error"]["code"] == "leave_overlap"
    # Staff can't approve leave.
    assert (
        rec.post(f"/api/v1/leave/{leave['id']}/decide", json={"decision": "approved"}).status_code
        == 403
    )

    pending = owner.get("/api/v1/leave").json()
    assert [p["id"] for p in pending] == [leave["id"]]
    decided = owner.post(
        f"/api/v1/leave/{leave['id']}/decide", json={"decision": "approved"}
    ).json()
    assert decided["status"] == "approved" and decided["shifts_affected"] == 1
    assert decided["blocks_bookings"] is False  # not a practitioner
    on_leave = shift(owner, clinic, rec.membership_id, week + timedelta(days=2))
    assert on_leave.json()["error"]["code"] == "on_leave"

    # Colleagues see who is away, not why.
    colleague = add_member(owner, "receptionist")
    roster = colleague.get(
        "/api/v1/roster", params={"branch_id": clinic["branch_id"], "start": week.isoformat()}
    ).json()
    away = next(lv for lv in roster["leave"] if lv["id"] == leave["id"])
    assert away["leave_type"] is None and away["reason"] is None
    assert colleague.get("/api/v1/leave").status_code == 403
    # The audit log doesn't carry the reason either.
    entries = owner.get("/api/v1/audit-logs", params={"limit": 200}).json()["items"]
    assert "Synthetic test reason" not in str([e["details"] for e in entries])

    # Nobody approves their own leave.
    own = owner.post(
        "/api/v1/leave",
        json={
            "membership_id": membership_id(owner),
            "starts_on": week.isoformat(),
            "ends_on": week.isoformat(),
            "leave_type": "annual",
            "approve": True,
        },
    )
    assert own.json()["error"]["code"] == "own_leave"


def test_practitioner_leave_blocks_bookings(clinic):
    owner, doctor, rec = clinic["owner"], clinic["doctor"], clinic["receptionist"]
    patient = make_patient(rec)
    day = date.today() + timedelta(days=10)
    booked = book(rec, clinic, patient["id"], at(day, "09:00"))
    assert booked.status_code == 201, booked.text
    leave = doctor.post(
        "/api/v1/me/leave",
        json={
            "starts_on": day.isoformat(),
            "ends_on": (day + timedelta(days=1)).isoformat(),
            "leave_type": "annual",
        },
    ).json()
    approved = owner.post(
        f"/api/v1/leave/{leave['id']}/decide", json={"decision": "approved"}
    ).json()
    assert approved["blocks_bookings"] is True
    assert approved["appointments_affected"] == 1  # reported, never cancelled automatically
    assert rec.get(f"/api/v1/appointments/{booked.json()['id']}").json()["status"] != "cancelled"
    blocked = book(
        rec, clinic, make_patient(rec, "Other")["id"], at(day + timedelta(days=1), "10:00")
    )
    assert blocked.status_code in (409, 422)
    # Cancelling the leave reopens the diary.
    cancelled = doctor.post(f"/api/v1/leave/{leave['id']}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["blocks_bookings"] is False
    reopened = book(
        rec, clinic, make_patient(rec, "Third")["id"], at(day + timedelta(days=1), "10:00")
    )
    assert reopened.status_code == 201, reopened.text


def test_branch_managers_and_tenants(clinic, add_member, new_actor):
    owner, rec = clinic["owner"], clinic["receptionist"]
    other = owner.post("/api/v1/branches", json={"name": "Walvis Bay", "branch_code": "WVB"}).json()
    manager = add_member(owner, "branch_manager", branch_id=other["id"])
    week = monday()
    # Can't roster someone into a branch they don't manage.
    assert shift(manager, clinic, rec.membership_id, week).status_code == 403
    wvb = add_member(owner, "receptionist", branch_id=other["id"])
    ok = manager.post(
        "/api/v1/shifts",
        json={
            "branch_id": other["id"],
            "membership_id": wvb.membership_id,
            "starts_at": at(week, "08:00"),
            "ends_at": at(week, "13:00"),
        },
    )
    assert ok.status_code == 201, ok.text
    # Leave: a branch manager decides only for staff who work in their branch.
    mine = wvb.post(
        "/api/v1/me/leave",
        json={"starts_on": week.isoformat(), "ends_on": week.isoformat(), "leave_type": "family"},
    ).json()
    theirs = rec.post(
        "/api/v1/me/leave",
        json={"starts_on": week.isoformat(), "ends_on": week.isoformat(), "leave_type": "annual"},
    ).json()
    assert [lv["id"] for lv in manager.get("/api/v1/leave").json()] == [mine["id"]]
    assert (
        manager.post(
            f"/api/v1/leave/{theirs['id']}/decide", json={"decision": "approved"}
        ).status_code
        == 403
    )
    assert (
        manager.post(
            f"/api/v1/leave/{mine['id']}/decide", json={"decision": "declined"}
        ).status_code
        == 200
    )

    stranger = new_actor()
    stranger.org_id = stranger.post("/api/v1/organisations", json={"name": "Else"}).json()["id"]
    assert (
        stranger.post(
            f"/api/v1/leave/{theirs['id']}/decide", json={"decision": "approved"}
        ).status_code
        == 404
    )
    assert stranger.post(f"/api/v1/shifts/{ok.json()['id']}/cancel").status_code == 404
    foreign = stranger.post(
        "/api/v1/shifts",
        json={
            "branch_id": main_branch_of(stranger),
            "membership_id": rec.membership_id,
            "starts_at": at(week, "08:00"),
            "ends_at": at(week, "10:00"),
        },
    )
    assert foreign.status_code == 422


def main_branch_of(actor) -> str:
    return actor.get("/api/v1/branches").json()["items"][0]["id"]


def test_unverified_is_irrelevant_for_rostering(clinic, add_member):
    """Rostering isn't clinical: an unverified practitioner can still be rostered."""
    owner = clinic["owner"]
    newcomer = add_member(owner, "practitioner")
    assert shift(owner, clinic, newcomer.membership_id, monday()).status_code == 201
    verify_practitioner(owner, newcomer)
