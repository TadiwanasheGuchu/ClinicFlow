from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from tests.conftest import book, local_time, make_patient

D = Decimal


def today() -> date:
    return datetime.now(ZoneInfo("Africa/Windhoek")).date()


@pytest.fixture
def activity(clinic):
    """Yesterday: one no-show (booked late as an audited override). Tomorrow: one completed
    consultation and one cancellation. One invoice part-paid."""
    owner, rec, doctor = clinic["owner"], clinic["receptionist"], clinic["doctor"]
    p1, p2, p3 = make_patient(rec), make_patient(rec), make_patient(rec)
    missed = book(owner, clinic, p1["id"], local_time(-1, "09:00"), override_reason="Back-entered")
    assert missed.status_code == 201, missed.text
    owner.post(f"/api/v1/appointments/{missed.json()['id']}/status", json={"status": "no_show"})
    done = book(rec, clinic, p2["id"], local_time(1, "09:00")).json()
    rec.post(f"/api/v1/appointments/{done['id']}/status", json={"status": "checked_in"})
    rec.post(f"/api/v1/appointments/{done['id']}/status", json={"status": "in_consultation"})
    assert (
        doctor.post(
            f"/api/v1/appointments/{done['id']}/status", json={"status": "completed"}
        ).status_code
        == 200
    )
    gone = book(rec, clinic, p3["id"], local_time(1, "11:00")).json()
    rec.post(f"/api/v1/appointments/{gone['id']}/cancel", json={"reason": "Patient called"})
    inv = rec.post(
        "/api/v1/invoices", json={"patient_id": p2["id"], "appointment_id": done["id"]}
    ).json()
    rec.post(f"/api/v1/invoices/{inv['id']}/issue")
    rec.post(f"/api/v1/invoices/{inv['id']}/payments", json={"amount": "300", "method": "cash"})
    return clinic


def params(**extra):
    return {
        "start": (today() - timedelta(days=1)).isoformat(),
        "end": (today() + timedelta(days=1)).isoformat(),
        **extra,
    }


def test_operational_report(activity):
    owner = activity["owner"]
    report = owner.get("/api/v1/reports/operational", params=params())
    assert report.status_code == 200, report.text
    r = report.json()
    assert (
        r["totals"]["booked"],
        r["totals"]["completed"],
        r["totals"]["cancelled"],
        r["totals"]["no_show"],
    ) == (3, 1, 1, 1)
    assert D(r["cancellation_rate_percent"]) == D("33.3")
    assert D(r["no_show_rate_percent"]) == D("50.0")  # 1 of 2 that were due to attend
    assert len(r["daily"]) == 3 and sum(d["booked"] for d in r["daily"]) == 3
    assert r["wait_sample"] == 1 and r["average_wait_minutes"] is not None
    assert r["new_patients"] >= 3
    provider = r["by_provider"][0]
    assert provider["available_minutes"] == 3 * 9 * 60  # 08:00-17:00 for three days
    # Occupied: the completed 30 minutes (cancelled and no-show free their time).
    assert provider["booked_minutes"] == 30
    assert D(provider["utilisation_percent"]) == D("1.9")


def test_financial_report(activity):
    owner = activity["owner"]
    r = owner.get("/api/v1/reports/financial", params=params()).json()
    assert D(r["invoiced"]) == D("450.00") and r["invoice_count"] == 1
    assert D(r["collected"]) == D("300.00") and D(r["net_collected"]) == D("300.00")
    assert [(m["key"], D(m["amount"])) for m in r["collected_by_method"]] == [("cash", D("300.00"))]
    assert r["revenue_by_provider"][0]["label"] != "Not linked to an appointment"
    assert D(r["outstanding_total"]) == D("150.00")
    assert next(b for b in r["aged_debt"] if b["bucket"] == "not_due")["invoices"] == 1
    assert len(r["series"]) == 1 and D(r["series"][0]["invoiced"]) == D("450.00")


def test_report_permissions_and_validation(activity, add_member, new_actor):
    owner = activity["owner"]
    assert (
        activity["receptionist"].get("/api/v1/reports/operational", params=params()).status_code
        == 403
    )
    manager = add_member(owner, "practice_manager")
    assert manager.get("/api/v1/reports/financial", params=params()).status_code == 200
    branch_manager = add_member(owner, "branch_manager", branch_id=activity["branch_id"])
    assert branch_manager.get("/api/v1/reports/operational", params=params()).status_code == 200
    assert branch_manager.get("/api/v1/reports/financial", params=params()).status_code == 403
    bad = owner.get(
        "/api/v1/reports/operational", params={"start": "2026-02-01", "end": "2026-01-01"}
    )
    assert bad.status_code == 422
    too_long = owner.get(
        "/api/v1/reports/financial", params={"start": "2025-01-01", "end": "2026-06-01"}
    )
    assert too_long.status_code == 422
    other = new_actor()
    other.org_id = other.post("/api/v1/organisations", json={"name": "Elsewhere"}).json()["id"]
    r = other.get("/api/v1/reports/operational", params=params()).json()
    assert r["totals"]["booked"] == 0
    assert D(other.get("/api/v1/reports/financial", params=params()).json()["invoiced"]) == D("0")
