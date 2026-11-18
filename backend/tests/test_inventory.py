"""Phase 6 — inventory. Stock changes only through the movement ledger, never goes negative,
leaves first-expiry-first-out, and is scoped by branch and tenant."""

from datetime import date, timedelta

import psycopg
import pytest

from tests.conftest import main_branch_id

FUTURE = (date.today() + timedelta(days=400)).isoformat()
SOONER = (date.today() + timedelta(days=60)).isoformat()


@pytest.fixture
def store(owner, add_member):
    branch = main_branch_id(owner)
    items = {}
    for sku, name, unit, reorder, track in (
        ("PCM500", "Paracetamol 500 mg tablets", "tablet", 100, True),
        ("GLV-M", "Examination gloves, medium", "box", 2, False),
    ):
        r = owner.post(
            "/api/v1/inventory/items",
            json={
                "sku": sku,
                "name": name,
                "unit": unit,
                "reorder_level": reorder,
                "track_expiry": track,
                "category": "Consumables",
            },
        )
        assert r.status_code == 201, r.text
        items[sku] = r.json()
    supplier = owner.post("/api/v1/inventory/suppliers", json={"name": "Example Medical Supplies"})
    assert supplier.status_code == 201, supplier.text
    return {
        "owner": owner,
        "branch": branch,
        "items": items,
        "supplier": supplier.json(),
        "nurse": None,
        "add_member": add_member,
    }


def receive(actor, store, sku="PCM500", quantity=200, **extra):
    body = {
        "branch_id": store["branch"],
        "item_id": store["items"][sku]["id"],
        "quantity": quantity,
        "unit_cost": "0.50",
        "batch_number": "B-1",
        "expiry_date": FUTURE,
        **extra,
    }
    return actor.post("/api/v1/inventory/receipts", json=body)


def level(actor, store, sku):
    levels = actor.get("/api/v1/inventory/stock", params={"include_empty": True}).json()["levels"]
    return next(lv for lv in levels if lv["sku"] == sku and lv["branch_id"] == store["branch"])


def test_purchase_order_to_stock(store):
    owner, pcm = store["owner"], store["items"]["PCM500"]
    po = owner.post(
        "/api/v1/inventory/purchase-orders",
        json={
            "branch_id": store["branch"],
            "supplier_id": store["supplier"]["id"],
            "lines": [{"item_id": pcm["id"], "quantity_ordered": 500, "unit_cost": "0.45"}],
        },
    )
    assert po.status_code == 201, po.text
    po = po.json()
    assert po["order_number"].startswith("PO-") and po["total"] == "225.00"
    line = po["lines"][0]["id"]
    url = f"/api/v1/inventory/purchase-orders/{po['id']}"
    early = owner.post(f"{url}/receive", json={"lines": [{"line_id": line, "quantity": 1}]})
    assert early.json()["error"]["code"] == "not_ordered"
    assert owner.post(f"{url}/place").json()["status"] == "ordered"
    # Placed orders can't be edited.
    edit = owner.put(
        url,
        json={
            "branch_id": store["branch"],
            "supplier_id": store["supplier"]["id"],
            "lines": [{"item_id": pcm["id"], "quantity_ordered": 1, "unit_cost": "1"}],
        },
    )
    assert edit.json()["error"]["code"] == "not_draft"
    # Medicines need a batch number and expiry date.
    missing = owner.post(f"{url}/receive", json={"lines": [{"line_id": line, "quantity": 300}]})
    assert missing.status_code == 422
    part = owner.post(
        f"{url}/receive",
        json={
            "lines": [
                {"line_id": line, "quantity": 300, "batch_number": "P1", "expiry_date": FUTURE}
            ]
        },
    )
    assert part.json()["status"] == "partially_received"
    over = owner.post(
        f"{url}/receive",
        json={
            "lines": [
                {"line_id": line, "quantity": 201, "batch_number": "P2", "expiry_date": FUTURE}
            ]
        },
    )
    assert over.json()["error"]["code"] == "over_received"
    done = owner.post(
        f"{url}/receive",
        json={
            "lines": [
                {"line_id": line, "quantity": 200, "batch_number": "P2", "expiry_date": FUTURE}
            ]
        },
    )
    assert done.json()["status"] == "received"
    assert owner.post(f"{url}/cancel", json={"reason": "Too late"}).status_code == 409
    lv = level(owner, store, "PCM500")
    assert lv["on_hand"] == 500 and lv["value"] == "225.00" and not lv["below_reorder"]


def test_usage_is_first_expiry_first_out(store):
    owner = store["owner"]
    assert (
        receive(owner, store, quantity=100, batch_number="LATE", expiry_date=FUTURE).status_code
        == 201
    )
    assert (
        receive(owner, store, quantity=30, batch_number="SOON", expiry_date=SOONER).status_code
        == 201
    )
    used = owner.post(
        "/api/v1/inventory/usage",
        json={
            "branch_id": store["branch"],
            "item_id": store["items"]["PCM500"]["id"],
            "quantity": 40,
            "reason": "Treatment room",
        },
    )
    assert used.status_code == 200, used.text
    by_batch = {b["batch_number"]: b["quantity_remaining"] for b in used.json()}
    assert by_batch == {"SOON": 0, "LATE": 90}
    lv = level(owner, store, "PCM500")
    assert lv["on_hand"] == 90 and lv["below_reorder"] is True
    too_much = owner.post(
        "/api/v1/inventory/usage",
        json={
            "branch_id": store["branch"],
            "item_id": store["items"]["PCM500"]["id"],
            "quantity": 91,
        },
    )
    assert too_much.json()["error"]["code"] == "insufficient_stock"
    assert too_much.json()["error"]["details"]["available"] == 90
    history = owner.get(
        "/api/v1/inventory/movements", params={"item_id": store["items"]["PCM500"]["id"]}
    ).json()
    assert [m["movement_type"] for m in history["items"]].count("usage") == 2


def test_expired_stock_is_never_issued(store, app_db):
    owner = store["owner"]
    receive(owner, store, quantity=10, batch_number="OK", expiry_date=FUTURE)
    assert receive(owner, store, batch_number="OLD", expiry_date="2020-01-01").status_code == 422
    # Seed an expired batch through the ledger, as if it had been received long ago.
    item = store["items"]["PCM500"]["id"]
    with app_db.transaction():
        app_db.execute("SELECT set_config('app.organisation_id', %s, true)", (owner.org_id,))
        batch = app_db.execute(
            "INSERT INTO stock_batches (id, organisation_id, item_id, branch_id, batch_number,"
            " expiry_date, unit_cost, quantity_received, quantity_remaining, received_at,"
            " created_at, updated_at) VALUES (gen_random_uuid(), %s, %s, %s, 'OLD', '2020-01-01',"
            " 1, 50, 0, now(), now(), now()) RETURNING id",
            (owner.org_id, item, store["branch"]),
        ).fetchone()[0]
        user = app_db.execute("SELECT id FROM users LIMIT 1").fetchone()[0]
        app_db.execute(
            "INSERT INTO stock_movements (id, organisation_id, branch_id, item_id, batch_id,"
            " movement_type, quantity, performed_by, occurred_at) VALUES (gen_random_uuid(),"
            " %s, %s, %s, %s, 'receipt', 50, %s, now())",
            (owner.org_id, store["branch"], item, batch, user),
        )
    lv = level(owner, store, "PCM500")
    assert lv["on_hand"] == 60 and lv["expired"] == 50 and lv["usable"] == 10
    use = {"branch_id": store["branch"], "item_id": item, "quantity": 11}
    assert (
        owner.post("/api/v1/inventory/usage", json=use).json()["error"]["code"]
        == "insufficient_stock"
    )
    off = owner.post(
        f"/api/v1/inventory/batches/{batch}/adjust",
        json={"kind": "write_off", "quantity": 50, "reason": "Expired"},
    )
    assert off.json()["quantity_remaining"] == 0


def test_counts_write_offs_and_transfers(store):
    owner = store["owner"]
    batch = receive(owner, store, "GLV-M", quantity=10, batch_number=None, expiry_date=None).json()
    url = f"/api/v1/inventory/batches/{batch['id']}"
    counted = owner.post(
        f"{url}/adjust", json={"kind": "count", "quantity": 8, "reason": "Monthly count"}
    )
    assert counted.json()["quantity_remaining"] == 8
    same = owner.post(f"{url}/adjust", json={"kind": "count", "quantity": 8, "reason": "Again"})
    assert same.status_code == 409
    too_many = owner.post(
        f"{url}/adjust", json={"kind": "write_off", "quantity": 9, "reason": "Torn"}
    )
    assert too_many.json()["error"]["code"] == "insufficient_stock"
    other = owner.post("/api/v1/branches", json={"name": "Walvis Bay", "branch_code": "WVB"}).json()
    moved = owner.post(f"{url}/transfer", json={"to_branch_id": other["id"], "quantity": 3})
    assert moved.status_code == 200, moved.text
    assert moved.json()["branch_id"] == other["id"] and moved.json()["quantity_remaining"] == 3
    batches = owner.get(f"/api/v1/inventory/items/{batch['item_id']}").json()["batches"]
    assert sorted(b["quantity_remaining"] for b in batches) == [3, 5]
    types = [
        m["movement_type"]
        for m in owner.get(
            "/api/v1/inventory/movements", params={"item_id": batch["item_id"]}
        ).json()["items"]
    ]
    assert sorted(types) == ["count", "receipt", "transfer_in", "transfer_out"]


def test_permissions_and_branch_scope(store, new_actor):
    owner, add_member = store["owner"], store["add_member"]
    batch = receive(owner, store).json()
    receptionist = add_member(owner, "receptionist")
    assert receptionist.get("/api/v1/inventory/stock").status_code == 403
    nurse = add_member(owner, "nurse")
    # Nurses record usage but don't count, write off or change the item list.
    use = {"branch_id": store["branch"], "item_id": batch["item_id"], "quantity": 2}
    assert nurse.post("/api/v1/inventory/usage", json=use).status_code == 200
    adjust = {"kind": "write_off", "quantity": 1, "reason": "Dropped"}
    assert (
        nurse.post(f"/api/v1/inventory/batches/{batch['id']}/adjust", json=adjust).status_code
        == 403
    )
    assert (
        nurse.post(
            "/api/v1/inventory/items", json={"sku": "X", "name": "Xx", "unit": "each"}
        ).status_code
        == 403
    )
    # A branch-scoped manager can't act on another branch's stock.
    other = owner.post("/api/v1/branches", json={"name": "Walvis Bay", "branch_code": "WVB"}).json()
    elsewhere = add_member(owner, "branch_manager", branch_id=other["id"])
    assert elsewhere.post("/api/v1/inventory/usage", json=use).status_code == 403
    levels = elsewhere.get("/api/v1/inventory/stock", params={"include_empty": True}).json()
    assert {lv["branch_id"] for lv in levels["levels"]} == {other["id"]}
    # Another organisation sees nothing.
    stranger = new_actor()
    stranger.org_id = stranger.post("/api/v1/organisations", json={"name": "Else"}).json()["id"]
    assert stranger.get(f"/api/v1/inventory/items/{batch['item_id']}").status_code == 404
    assert (
        stranger.post(f"/api/v1/inventory/batches/{batch['id']}/adjust", json=adjust).status_code
        == 404
    )
    assert stranger.get("/api/v1/inventory/movements").json()["total"] == 0


def test_ledger_is_enforced_by_the_database(store, app_db):
    owner = store["owner"]
    batch = receive(owner, store, quantity=5).json()
    statements = [
        ("UPDATE stock_batches SET quantity_remaining = 999 WHERE id = %s", batch["id"]),
        ("UPDATE stock_batches SET unit_cost = 0 WHERE id = %s", batch["id"]),
        ("DELETE FROM stock_batches WHERE id = %s", batch["id"]),
        ("UPDATE stock_movements SET quantity = 999 WHERE batch_id = %s", batch["id"]),
        ("DELETE FROM stock_movements WHERE batch_id = %s", batch["id"]),
        (
            "INSERT INTO stock_movements (id, organisation_id, branch_id, item_id, batch_id,"
            " movement_type, quantity, performed_by, occurred_at) SELECT gen_random_uuid(),"
            " organisation_id, branch_id, item_id, id, 'usage', -6,"
            " (SELECT id FROM users LIMIT 1), now() FROM stock_batches WHERE id = %s",
            batch["id"],
        ),
    ]
    for sql, arg in statements:
        with app_db.transaction():
            app_db.execute("SELECT set_config('app.organisation_id', %s, true)", (owner.org_id,))
            with pytest.raises(
                (
                    psycopg.errors.RaiseException,
                    psycopg.errors.InsufficientPrivilege,
                    psycopg.errors.CheckViolation,
                )
            ):
                app_db.execute(sql, (arg,))
