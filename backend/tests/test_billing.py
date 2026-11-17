"""Acceptance (Phase 5): a consultation generates an invoice; payments reconcile; claim
statuses are tracked; financial history stays auditable."""

import threading
from decimal import Decimal

import psycopg
import pytest

from tests.conftest import book, local_time, make_patient

D = Decimal


def service(owner, code, price, tax="standard"):
    response = owner.post(
        "/api/v1/services",
        json={"code": code, "name": f"Service {code}", "unit_price": price, "tax_category": tax},
    )
    assert response.status_code == 201, response.text
    return response.json()


def issued_invoice(actor, clinic, patient_id, items):
    draft = actor.post(
        "/api/v1/invoices",
        json={"patient_id": patient_id, "branch_id": clinic["branch_id"], "items": items},
    )
    assert draft.status_code == 201, draft.text
    issued = actor.post(f"/api/v1/invoices/{draft.json()['id']}/issue")
    assert issued.status_code == 200, issued.text
    return issued.json()


def pay(actor, invoice_id, amount, method="cash"):
    return actor.post(
        f"/api/v1/invoices/{invoice_id}/payments", json={"amount": amount, "method": method}
    )


def test_vat_and_rounding(clinic):
    owner = clinic["owner"]
    owner.patch(
        "/api/v1/organisation", json={"settings": {"vat_registered": True, "vat_rate": "15.00"}}
    )
    a = service(owner, "CONS", "450.00")
    b = service(owner, "DRESS", "120.50", tax="exempt")
    patient = make_patient(owner)
    inv = issued_invoice(
        owner,
        clinic,
        patient["id"],
        [
            {"service_id": a["id"]},
            {"service_id": b["id"], "quantity": "2"},
            {"description": "Consumables", "unit_price": "33.33", "quantity": "3"},
        ],
    )
    # 450 + 241 + 99.99 = 790.99; VAT 15% on 450 (67.50) and 99.99 (14.9985 -> 15.00)
    assert D(inv["subtotal"]) == D("790.99")
    assert D(inv["tax_amount"]) == D("82.50")
    assert D(inv["total"]) == D("873.49")
    assert [D(i["tax_rate"]) for i in inv["items"]] == [D("15.00"), D("0.00"), D("15.00")]
    assert inv["invoice_number"] == "INV-000001"

    owner.patch("/api/v1/organisation", json={"settings": {"vat_registered": False}})
    plain = issued_invoice(owner, clinic, patient["id"], [{"service_id": a["id"]}])
    assert D(plain["tax_amount"]) == D("0.00") and D(plain["total"]) == D("450.00")
    assert plain["invoice_number"] == "INV-000002"


def test_invoice_from_appointment_and_immutability(clinic, app_db):
    rec = clinic["receptionist"]
    patient = make_patient(rec)
    appt = book(rec, clinic, patient["id"], local_time(1, "09:00")).json()
    draft = rec.post(
        "/api/v1/invoices", json={"patient_id": patient["id"], "appointment_id": appt["id"]}
    ).json()
    assert draft["status"] == "draft" and draft["invoice_number"] is None
    assert draft["items"][0]["description"] == "Consultation" and D(draft["total"]) == D("450.00")
    edited = rec.put(
        f"/api/v1/invoices/{draft['id']}/items",
        json={
            "items": [
                {"description": "Consultation", "unit_price": "450.00"},
                {"description": "Dressing", "unit_price": "80.00"},
            ]
        },
    )
    assert D(edited.json()["total"]) == D("530.00")
    issued = rec.post(f"/api/v1/invoices/{draft['id']}/issue").json()
    assert issued["status"] == "issued" and issued["due_at"]
    assert (
        rec.put(f"/api/v1/invoices/{draft['id']}/items", json={"items": []}).json()["error"]["code"]
        == "invoice_issued"
    )
    assert rec.delete(f"/api/v1/invoices/{draft['id']}").status_code == 409
    for statement in (
        "UPDATE invoices SET total = 1, subtotal = 1 WHERE id = %s",
        "DELETE FROM invoices WHERE id = %s",
        "UPDATE invoice_items SET unit_price = 1 WHERE invoice_id = %s",
    ):
        with pytest.raises(psycopg.errors.RaiseException), app_db.transaction():
            app_db.execute("SELECT set_config('app.organisation_id', %s, true)", (rec.org_id,))
            app_db.execute(statement, (draft["id"],))
    # Drafts can be discarded.
    other = rec.post(
        "/api/v1/invoices",
        json={
            "patient_id": patient["id"],
            "branch_id": clinic["branch_id"],
            "items": [{"description": "Form", "unit_price": "50"}],
        },
    ).json()
    assert rec.delete(f"/api/v1/invoices/{other['id']}").status_code == 204


def test_payments_reconcile(clinic):
    rec, owner = clinic["receptionist"], clinic["owner"]
    patient = make_patient(rec)
    draft = rec.post(
        "/api/v1/invoices",
        json={
            "patient_id": patient["id"],
            "branch_id": clinic["branch_id"],
            "items": [{"description": "Consultation", "unit_price": "450"}],
        },
    ).json()
    assert pay(rec, draft["id"], "100").json()["error"]["message"].startswith("Issue the invoice")
    rec.post(f"/api/v1/invoices/{draft['id']}/issue")
    first = pay(rec, draft["id"], "200", "card").json()
    assert first["receipt_number"] == "RC-000001"
    inv = rec.get(f"/api/v1/invoices/{draft['id']}").json()
    assert inv["status"] == "partially_paid" and D(inv["amount_due"]) == D("250.00")
    over = pay(rec, draft["id"], "250.01")
    assert over.status_code == 422 and over.json()["error"]["code"] == "overpayment"
    pay(rec, draft["id"], "250", "eft")
    inv = rec.get(f"/api/v1/invoices/{draft['id']}").json()
    assert inv["status"] == "paid" and D(inv["amount_due"]) == D("0.00")
    assert D(inv["amount_paid"]) == D("450.00")
    logs = owner.get("/api/v1/audit-logs", params={"action": "payment.recorded"}).json()
    assert logs["total"] == 2


def test_concurrent_payments_cannot_overpay(clinic):
    rec = clinic["receptionist"]
    patient = make_patient(rec)
    inv = issued_invoice(
        rec, clinic, patient["id"], [{"description": "Consultation", "unit_price": "450"}]
    )
    barrier = threading.Barrier(2)
    codes: list[int] = []

    def attempt():
        barrier.wait()
        codes.append(pay(rec, inv["id"], "450").status_code)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(codes) == [201, 422]
    assert D(rec.get(f"/api/v1/invoices/{inv['id']}").json()["amount_paid"]) == D("450.00")


def test_credit_notes_and_refunds(clinic, add_member):
    rec, owner = clinic["receptionist"], clinic["owner"]
    billing = add_member(owner, "billing_officer")
    patient = make_patient(rec)
    inv = issued_invoice(
        rec, clinic, patient["id"], [{"description": "Consultation", "unit_price": "450"}]
    )
    pay(rec, inv["id"], "450")
    # Receptionists can't adjust.
    assert (
        rec.post(
            f"/api/v1/invoices/{inv['id']}/credit-notes",
            json={"amount": "50", "reason": "Discount"},
        ).status_code
        == 403
    )
    nothing_to_refund = billing.post(
        f"/api/v1/invoices/{inv['id']}/refunds",
        json={"amount": "10", "method": "cash", "reason": "Test"},
    )
    assert nothing_to_refund.json()["error"]["code"] == "refund_exceeds_credit"
    credited = billing.post(
        f"/api/v1/invoices/{inv['id']}/credit-notes",
        json={"amount": "450", "reason": "Consultation not completed"},
    ).json()
    assert credited["status"] == "credited" and D(credited["credit_balance"]) == D("450.00")
    assert credited["credit_notes"][0]["credit_note_number"] == "CN-000001"
    assert (
        billing.post(
            f"/api/v1/invoices/{inv['id']}/credit-notes", json={"amount": "1", "reason": "Again"}
        ).status_code
        == 422
    )
    refunded = billing.post(
        f"/api/v1/invoices/{inv['id']}/refunds",
        json={"amount": "450", "method": "cash", "reason": "Returned to patient"},
    ).json()
    assert (
        D(refunded["credit_balance"]) == D("0.00")
        and refunded["refunds"][0]["refund_number"] == "RF-000001"
    )
    statement = rec.get(f"/api/v1/patients/{patient['id']}/statement").json()
    assert [line["kind"] for line in statement["lines"]] == [
        "invoice",
        "payment",
        "credit_note",
        "refund",
    ]
    assert D(statement["balance"]) == D("0.00")


def test_payment_reversal(clinic, add_member, app_db):
    rec, owner = clinic["receptionist"], clinic["owner"]
    billing = add_member(owner, "billing_officer")
    patient = make_patient(rec)
    inv = issued_invoice(
        rec, clinic, patient["id"], [{"description": "Consultation", "unit_price": "450"}]
    )
    payment = pay(rec, inv["id"], "200").json()
    assert (
        rec.post(
            f"/api/v1/payments/{payment['id']}/reverse", json={"reason": "Card declined"}
        ).status_code
        == 403
    )
    reversed_ = billing.post(
        f"/api/v1/payments/{payment['id']}/reverse", json={"reason": "Card declined"}
    ).json()
    assert reversed_["status"] == "issued" and D(reversed_["amount_paid"]) == D("0.00")
    assert reversed_["payments"][0]["status"] == "reversed"
    assert (
        billing.post(
            f"/api/v1/payments/{payment['id']}/reverse", json={"reason": "Again"}
        ).status_code
        == 409
    )
    refused = (psycopg.errors.RaiseException, psycopg.errors.InsufficientPrivilege)
    for statement in (
        "UPDATE payments SET amount = 1 WHERE id = %s",
        "DELETE FROM payments WHERE id = %s",
    ):
        with pytest.raises(refused), app_db.transaction():
            app_db.execute("SELECT set_config('app.organisation_id', %s, true)", (rec.org_id,))
            app_db.execute(statement, (payment["id"],))
    with (
        pytest.raises((psycopg.errors.RaiseException, psycopg.errors.InsufficientPrivilege)),
        app_db.transaction(),
    ):
        app_db.execute("SELECT set_config('app.organisation_id', %s, true)", (rec.org_id,))
        app_db.execute("DELETE FROM credit_notes")


def test_cash_up(clinic, add_member):
    from datetime import date

    rec, owner = clinic["receptionist"], clinic["owner"]
    billing = add_member(owner, "billing_officer")
    patient = make_patient(rec)
    a = issued_invoice(
        rec, clinic, patient["id"], [{"description": "Consultation", "unit_price": "450"}]
    )
    b = issued_invoice(
        rec, clinic, patient["id"], [{"description": "Consultation", "unit_price": "300"}]
    )
    pay(rec, a["id"], "450", "cash")
    card = pay(rec, b["id"], "300", "card").json()
    billing.post(f"/api/v1/payments/{card['id']}/reverse", json={"reason": "Duplicate swipe"})
    billing.post(
        f"/api/v1/invoices/{a['id']}/credit-notes", json={"amount": "50", "reason": "Discount"}
    )
    billing.post(
        f"/api/v1/invoices/{a['id']}/refunds",
        json={"amount": "50", "method": "cash", "reason": "Discount"},
    )
    from datetime import datetime
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("Africa/Windhoek")).date().isoformat()
    report = rec.get("/api/v1/billing/cash-up", params={"date": today}).json()
    cash = next(m for m in report["by_method"] if m["method"] == "cash")
    assert (
        D(cash["received"]) == D("450.00")
        and D(cash["refunded"]) == D("50.00")
        and D(cash["net"]) == D("400.00")
    )
    assert not any(m["method"] == "card" for m in report["by_method"])  # reversed
    assert len(report["reversed_payments"]) == 1
    assert D(report["net"]) == D("400.00")
    assert date.fromisoformat(report["date"])


def test_medical_aid_claim_lifecycle(clinic, add_member, app_db):
    owner, rec, doctor = clinic["owner"], clinic["receptionist"], clinic["doctor"]
    billing = add_member(owner, "billing_officer")
    manager = add_member(owner, "practice_manager")
    fund = owner.post("/api/v1/medical-aid/funds", json={"name": "Example Medical Fund"}).json()
    patient = make_patient(rec)
    membership = rec.post(
        f"/api/v1/patients/{patient['id']}/medical-aid",
        json={
            "fund_id": fund["id"],
            "membership_number": "EX123456",
            "dependant_code": "00",
            "plan_name": "Standard",
        },
    ).json()
    verified = rec.post(
        f"/api/v1/medical-aid/memberships/{membership['id']}/verify",
        json={"method": "verified_by_phone", "note": "Called fund"},
    ).json()
    assert verified["verification_status"] == "verified_by_phone"

    # Consultation with a coded diagnosis, then an invoice for the appointment.
    appt = book(rec, clinic, patient["id"], local_time(1, "10:00")).json()
    rec.post(f"/api/v1/appointments/{appt['id']}/status", json={"status": "checked_in"})
    encounter = doctor.post(
        "/api/v1/encounters", json={"patient_id": patient["id"], "appointment_id": appt["id"]}
    ).json()
    doctor.post(
        f"/api/v1/encounters/{encounter['id']}/diagnoses",
        json={"description": "URTI", "code": "J06.9"},
    )
    inv = rec.post(
        "/api/v1/invoices", json={"patient_id": patient["id"], "appointment_id": appt["id"]}
    ).json()
    rec.post(f"/api/v1/invoices/{inv['id']}/issue")

    claim = billing.post(
        "/api/v1/claims", json={"invoice_id": inv["id"], "membership_id": membership["id"]}
    ).json()
    assert claim["status"] == "draft" and claim["diagnosis_codes"] == ["J06.9"]
    assert claim["claim_number"] == "CL-000001" and D(claim["claimed_amount"]) == D("450.00")
    assert claim["membership_snapshot"]["membership_number"] == "EX123456"
    dup = billing.post(
        "/api/v1/claims", json={"invoice_id": inv["id"], "membership_id": membership["id"]}
    )
    assert dup.json()["error"]["code"] == "claim_exists"
    # The diagnosis text never reaches billing staff.
    assert "URTI" not in str(billing.get(f"/api/v1/claims/{claim['id']}").json())

    url = f"/api/v1/claims/{claim['id']}"
    assert (
        billing.post(
            f"{url}/status", json={"status": "accepted", "approved_amount": "1"}
        ).status_code
        == 409
    )
    assert billing.post(f"{url}/status", json={"status": "ready"}).status_code == 200
    assert (
        billing.patch(url, json={"claimed_amount": "100"}).json()["error"]["code"]
        == "claim_not_draft"
    )
    with pytest.raises(psycopg.errors.RaiseException), app_db.transaction():
        app_db.execute("SELECT set_config('app.organisation_id', %s, true)", (owner.org_id,))
        app_db.execute(
            "UPDATE medical_aid_claims SET claimed_amount = 1 WHERE id = %s", (claim["id"],)
        )
    assert (
        billing.post(f"{url}/status", json={"status": "submitted"}).status_code == 422
    )  # method required
    billing.post(
        f"{url}/status",
        json={"status": "submitted", "submission_method": "email", "fund_reference": "FUND-778"},
    )
    accepted = billing.post(
        f"{url}/status", json={"status": "accepted", "approved_amount": "400"}
    ).json()
    assert D(accepted["patient_portion"]) == D("50.00")
    assert (
        manager.post(f"{url}/remittance", json={"amount": "400", "reference": "REM-1"}).status_code
        == 403
    )
    assert manager.get(url).status_code == 200  # read-only access
    too_much = billing.post(f"{url}/remittance", json={"amount": "400.01", "reference": "REM-1"})
    assert too_much.status_code == 422
    remitted = billing.post(
        f"{url}/remittance", json={"amount": "400", "reference": "REM-1"}
    ).json()
    assert remitted["method"] == "medical_aid"
    detail = billing.get(url).json()
    assert detail["status"] == "paid" and D(detail["paid_amount"]) == D("400.00")
    assert [e["event_type"] for e in detail["events"]] == [
        "prepared",
        "status_changed",
        "status_changed",
        "status_changed",
        "remittance_recorded",
    ]
    invoice = rec.get(f"/api/v1/invoices/{inv['id']}").json()
    assert invoice["status"] == "partially_paid" and D(invoice["amount_due"]) == D("50.00")
    pay(rec, inv["id"], "50")
    assert rec.get(f"/api/v1/invoices/{inv['id']}").json()["status"] == "paid"

    # Reversing the fund's payment re-opens the claim.
    billing.post(
        f"/api/v1/payments/{remitted['id']}/reverse", json={"reason": "Fund recalled payment"}
    )
    assert billing.get(url).json()["status"] == "accepted"


def test_claim_needs_codes_and_rejection_path(clinic, add_member):
    owner, rec = clinic["owner"], clinic["receptionist"]
    billing = add_member(owner, "billing_officer")
    fund = owner.post("/api/v1/medical-aid/funds", json={"name": "Another Fund"}).json()
    patient = make_patient(rec)
    membership = rec.post(
        f"/api/v1/patients/{patient['id']}/medical-aid",
        json={"fund_id": fund["id"], "membership_number": "AF999"},
    ).json()
    inv = issued_invoice(
        rec, clinic, patient["id"], [{"description": "Consultation", "unit_price": "450"}]
    )
    claim = billing.post(
        "/api/v1/claims", json={"invoice_id": inv["id"], "membership_id": membership["id"]}
    ).json()
    url = f"/api/v1/claims/{claim['id']}"
    assert (
        billing.post(f"{url}/status", json={"status": "ready"}).json()["error"]["code"]
        == "diagnosis_codes_required"
    )
    assert billing.patch(url, json={"diagnosis_codes": ["not-a-code"]}).status_code == 422
    billing.patch(url, json={"diagnosis_codes": ["z00.0"]})
    billing.post(f"{url}/status", json={"status": "ready"})
    billing.post(f"{url}/status", json={"status": "submitted", "submission_method": "paper"})
    assert billing.post(f"{url}/status", json={"status": "rejected"}).status_code == 422  # reason
    rejected = billing.post(
        f"{url}/status", json={"status": "rejected", "reason": "Benefit exhausted"}
    ).json()
    assert D(rejected["patient_portion"]) == D("450.00")
    billing.post(
        f"{url}/status",
        json={"status": "resubmission_required", "reason": "Appeal with motivation"},
    )
    assert billing.post(f"{url}/status", json={"status": "draft"}).json()["status"] == "draft"
    assert billing.patch(url, json={"claimed_amount": "300"}).status_code == 200


def test_billing_permissions_and_isolation(clinic, add_member, new_actor):
    owner, rec = clinic["owner"], clinic["receptionist"]
    patient = make_patient(rec)
    inv = issued_invoice(
        rec, clinic, patient["id"], [{"description": "Consultation", "unit_price": "450"}]
    )
    nurse = add_member(owner, "nurse")
    assert nurse.get(f"/api/v1/invoices/{inv['id']}").status_code == 403
    assert (
        rec.post(
            "/api/v1/services", json={"code": "X", "name": "Xray", "unit_price": "1"}
        ).status_code
        == 403
    )
    other = new_actor()
    other.org_id = other.post("/api/v1/organisations", json={"name": "Elsewhere"}).json()["id"]
    assert other.get(f"/api/v1/invoices/{inv['id']}").status_code == 404
    assert pay(other, inv["id"], "1").status_code == 404
    assert other.get("/api/v1/invoices").json()["total"] == 0
