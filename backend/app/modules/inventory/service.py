"""Inventory service.

Permissions:
  inventory.read     stock levels, batches, history and purchase orders (per branch)
  inventory.manage   receive stock, record usage, transfer, raise and receive purchase orders
  inventory.adjust   stock counts and write-offs (per branch); the item list and suppliers
                     (organisation-wide)

Stock leaves in first-expiry-first-out order and expired batches are never issued; they
can only be written off. Every change is a ledger movement (see models), so the database
rejects anything that would take a batch below zero.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, NotFound, ValidationFailed
from app.core.tenancy import TenantContext, deny
from app.modules.branches.models import Branch
from app.modules.inventory.models import (
    InventoryItem,
    PurchaseOrder,
    PurchaseOrderLine,
    StockBatch,
    StockMovement,
    Supplier,
)
from app.modules.inventory.schemas import (
    Adjustment,
    BatchDetails,
    BatchRead,
    ItemRead,
    POLineRead,
    PORead,
    POReceipt,
    POWrite,
    ReceiptCreate,
    StockLevel,
    StockOverview,
    TransferCreate,
    UsageCreate,
)
from app.modules.users.models import User
from app.shared.counters import format_number, next_value

EXPIRY_WINDOW_DAYS = 90
CENT = Decimal("0.01")


def today(ctx: TenantContext) -> date:
    return datetime.now(ZoneInfo(ctx.organisation.timezone)).date()


def require_branch(ctx: TenantContext, permission: str, branch_id: uuid.UUID) -> None:
    if not ctx.has_in_branch(permission, branch_id):
        raise deny(ctx, permission, "stock")


def _get(db: Session, model: type, ident: uuid.UUID, what: str, *, lock: bool = False):  # type: ignore[no-untyped-def]
    row = db.get(model, ident, with_for_update=lock or None)
    if row is None:
        raise NotFound(f"{what} not found.")
    return row


def get_item(db: Session, item_id: uuid.UUID) -> InventoryItem:
    return _get(db, InventoryItem, item_id, "Item")


def get_batch(
    db: Session, ctx: TenantContext, batch_id: uuid.UUID, *, lock: bool = False
) -> StockBatch:
    batch: StockBatch = _get(db, StockBatch, batch_id, "Stock batch", lock=lock)
    require_branch(ctx, "inventory.read", batch.branch_id)
    return batch


def _branch(db: Session, branch_id: uuid.UUID) -> Branch:
    return _get(db, Branch, branch_id, "Branch")


def _move(
    db: Session,
    ctx: TenantContext,
    batch: StockBatch,
    movement_type: str,
    quantity: int,
    *,
    reason: str | None = None,
    reference: str | None = None,
    transfer_id: uuid.UUID | None = None,
) -> None:
    movement = StockMovement(
        organisation_id=ctx.organisation_id,
        branch_id=batch.branch_id,
        item_id=batch.item_id,
        batch_id=batch.id,
        movement_type=movement_type,
        quantity=quantity,
        reason=reason,
        reference=reference,
        transfer_id=transfer_id,
        performed_by=ctx.user_id,
        occurred_at=datetime.now(UTC),
    )
    try:
        with db.begin_nested():
            db.add(movement)
            db.flush()
    except IntegrityError as exc:
        raise Conflict("Not enough stock in this batch.", code="insufficient_stock") from exc
    db.refresh(batch)


def _check_batch_details(ctx: TenantContext, item: InventoryItem, details: BatchDetails) -> None:
    if item.track_expiry and not (details.batch_number and details.expiry_date):
        raise ValidationFailed(f"{item.name} needs a batch number and expiry date.")
    if details.expiry_date is not None and details.expiry_date < today(ctx):
        raise ValidationFailed("This stock has already expired; don't receive it.")


def _new_batch(
    db: Session,
    ctx: TenantContext,
    *,
    item: InventoryItem,
    branch_id: uuid.UUID,
    quantity: int,
    unit_cost: Decimal,
    details: BatchDetails,
    supplier_id: uuid.UUID | None = None,
    purchase_order_id: uuid.UUID | None = None,
) -> StockBatch:
    batch = StockBatch(
        organisation_id=ctx.organisation_id,
        item_id=item.id,
        branch_id=branch_id,
        batch_number=details.batch_number or None,
        expiry_date=details.expiry_date,
        unit_cost=unit_cost.quantize(CENT, ROUND_HALF_UP),
        quantity_received=quantity,
        quantity_remaining=0,
        supplier_id=supplier_id,
        purchase_order_id=purchase_order_id,
        received_at=datetime.now(UTC),
    )
    db.add(batch)
    db.flush()
    return batch


# --- Stock in and out --------------------------------------------------------------------


def receive(db: Session, ctx: TenantContext, data: ReceiptCreate) -> StockBatch:
    require_branch(ctx, "inventory.manage", data.branch_id)
    _branch(db, data.branch_id)
    item = get_item(db, data.item_id)
    if not item.is_active:
        raise ValidationFailed("This item is no longer stocked.")
    if data.supplier_id is not None:
        _get(db, Supplier, data.supplier_id, "Supplier")
    _check_batch_details(ctx, item, data)
    batch = _new_batch(
        db,
        ctx,
        item=item,
        branch_id=data.branch_id,
        quantity=data.quantity,
        unit_cost=data.unit_cost,
        details=data,
        supplier_id=data.supplier_id,
    )
    _move(db, ctx, batch, "receipt", data.quantity, reference=data.reference)
    ctx.audit(
        db,
        "stock.received",
        "stock_batch",
        batch.id,
        branch_id=batch.branch_id,
        details={"item_id": str(item.id), "quantity": data.quantity},
    )
    return batch


def use(db: Session, ctx: TenantContext, data: UsageCreate) -> list[StockBatch]:
    """Take stock first-expiry-first-out from batches that haven't expired."""
    require_branch(ctx, "inventory.manage", data.branch_id)
    item = get_item(db, data.item_id)
    batches = list(
        db.scalars(
            select(StockBatch)
            .where(
                StockBatch.item_id == item.id,
                StockBatch.branch_id == data.branch_id,
                StockBatch.quantity_remaining > 0,
                (StockBatch.expiry_date.is_(None)) | (StockBatch.expiry_date >= today(ctx)),
            )
            .order_by(StockBatch.expiry_date.nulls_last(), StockBatch.received_at)
            .with_for_update()
        )
    )
    available = sum(b.quantity_remaining for b in batches)
    if available < data.quantity:
        raise Conflict(
            f"Only {available} {item.unit} of {item.name} in date at this branch.",
            code="insufficient_stock",
            details={"available": available},
        )
    remaining, used = data.quantity, []
    for batch in batches:
        if remaining == 0:
            break
        take = min(remaining, batch.quantity_remaining)
        _move(db, ctx, batch, "usage", -take, reason=data.reason, reference=data.reference)
        remaining -= take
        used.append(batch)
    ctx.audit(
        db,
        "stock.used",
        "inventory_item",
        item.id,
        branch_id=data.branch_id,
        details={"quantity": data.quantity, "batches": len(used)},
    )
    return used


def adjust(db: Session, ctx: TenantContext, batch: StockBatch, data: Adjustment) -> None:
    require_branch(ctx, "inventory.adjust", batch.branch_id)
    if data.kind == "count":
        change = data.quantity - batch.quantity_remaining
        if change == 0:
            raise Conflict("The count matches the recorded stock; nothing to adjust.")
        _move(db, ctx, batch, "count", change, reason=data.reason)
    else:
        if data.quantity == 0:
            raise ValidationFailed("Enter the quantity to write off.")
        _move(db, ctx, batch, "write_off", -data.quantity, reason=data.reason)
        change = -data.quantity
    ctx.audit(
        db,
        f"stock.{data.kind}",
        "stock_batch",
        batch.id,
        branch_id=batch.branch_id,
        details={"item_id": str(batch.item_id), "change": change},
    )


def transfer(
    db: Session, ctx: TenantContext, batch: StockBatch, data: TransferCreate
) -> StockBatch:
    if data.to_branch_id == batch.branch_id:
        raise ValidationFailed("Choose a different branch.")
    require_branch(ctx, "inventory.manage", batch.branch_id)
    require_branch(ctx, "inventory.manage", data.to_branch_id)
    _branch(db, data.to_branch_id)
    if batch.expiry_date is not None and batch.expiry_date < today(ctx):
        raise Conflict("Expired stock can't be transferred; write it off instead.")
    item = get_item(db, batch.item_id)
    transfer_id = uuid.uuid4()
    _move(
        db, ctx, batch, "transfer_out", -data.quantity, reason=data.reason, transfer_id=transfer_id
    )
    arrived = _new_batch(
        db,
        ctx,
        item=item,
        branch_id=data.to_branch_id,
        quantity=data.quantity,
        unit_cost=batch.unit_cost,
        details=BatchDetails(batch_number=batch.batch_number, expiry_date=batch.expiry_date),
        supplier_id=batch.supplier_id,
    )
    _move(
        db, ctx, arrived, "transfer_in", data.quantity, reason=data.reason, transfer_id=transfer_id
    )
    ctx.audit(
        db,
        "stock.transferred",
        "stock_batch",
        batch.id,
        branch_id=batch.branch_id,
        details={
            "to_branch_id": str(data.to_branch_id),
            "quantity": data.quantity,
            "new_batch_id": str(arrived.id),
        },
    )
    return arrived


# --- Reading -----------------------------------------------------------------------------


def overview(
    db: Session, ctx: TenantContext, branch_id: uuid.UUID | None, include_empty: bool
) -> StockOverview:
    now = today(ctx)
    soon = now + timedelta(days=EXPIRY_WINDOW_DAYS)
    scope = ctx.branch_scope("inventory.read")
    branches = db.scalars(select(Branch).order_by(Branch.name)).all()
    branches = [
        b
        for b in branches
        if (scope is None or b.id in scope) and (branch_id is None or b.id == branch_id)
    ]
    items = db.scalars(
        select(InventoryItem).where(InventoryItem.is_active.is_(True)).order_by(InventoryItem.name)
    ).all()
    rows: dict[tuple[uuid.UUID, uuid.UUID], dict] = {}
    batches = db.scalars(
        select(StockBatch).where(
            StockBatch.quantity_remaining > 0, StockBatch.branch_id.in_([b.id for b in branches])
        )
    )
    for b in batches:
        r = rows.setdefault(
            (b.item_id, b.branch_id),
            {"on_hand": 0, "expired": 0, "soon": 0, "next": None, "value": Decimal(0)},
        )
        r["on_hand"] += b.quantity_remaining
        r["value"] += b.unit_cost * b.quantity_remaining
        if b.expiry_date is not None:
            if b.expiry_date < now:
                r["expired"] += b.quantity_remaining
            else:
                if b.expiry_date <= soon:
                    r["soon"] += b.quantity_remaining
                r["next"] = min(filter(None, [r["next"], b.expiry_date]))
    levels = []
    for item in items:
        for branch in branches:
            r = rows.get((item.id, branch.id))
            if r is None and not include_empty and item.reorder_level == 0:
                continue
            r = r or {"on_hand": 0, "expired": 0, "soon": 0, "next": None, "value": Decimal(0)}
            usable = r["on_hand"] - r["expired"]
            levels.append(
                StockLevel(
                    item_id=item.id,
                    sku=item.sku,
                    name=item.name,
                    category=item.category,
                    unit=item.unit,
                    reorder_level=item.reorder_level,
                    branch_id=branch.id,
                    branch_name=branch.name,
                    on_hand=r["on_hand"],
                    usable=usable,
                    expired=r["expired"],
                    expiring_soon=r["soon"],
                    next_expiry=r["next"],
                    value=r["value"].quantize(CENT, ROUND_HALF_UP),
                    below_reorder=usable <= item.reorder_level,
                )
            )
    total = sum((lv.value for lv in levels), Decimal(0)).quantize(CENT, ROUND_HALF_UP)
    return StockOverview(levels=levels, total_value=total, expiry_window_days=EXPIRY_WINDOW_DAYS)


def batch_reads(db: Session, ctx: TenantContext, rows: list[StockBatch]) -> list[BatchRead]:
    names = dict(
        db.execute(
            select(Supplier.id, Supplier.name).where(
                Supplier.id.in_({b.supplier_id for b in rows if b.supplier_id})
            )
        ).all()
    )
    now = today(ctx)
    return [
        BatchRead.model_validate(
            {
                **{
                    k: getattr(b, k)
                    for k in BatchRead.model_fields
                    if k not in ("supplier_name", "expired")
                },
                "supplier_name": names.get(b.supplier_id) if b.supplier_id else None,
                "expired": b.expiry_date is not None and b.expiry_date < now,
            }
        )
        for b in rows
    ]


def user_names(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    return dict(db.execute(select(User.id, User.full_name).where(User.id.in_(ids))).all())


def item_read(item: InventoryItem) -> ItemRead:
    return ItemRead.model_validate(item)


# --- Purchase orders ---------------------------------------------------------------------


def get_po(
    db: Session, ctx: TenantContext, po_id: uuid.UUID, *, lock: bool = False
) -> PurchaseOrder:
    po: PurchaseOrder = _get(db, PurchaseOrder, po_id, "Purchase order", lock=lock)
    require_branch(ctx, "inventory.read", po.branch_id)
    return po


def _lines(db: Session, po_id: uuid.UUID) -> list[PurchaseOrderLine]:
    return list(
        db.scalars(
            select(PurchaseOrderLine)
            .where(PurchaseOrderLine.purchase_order_id == po_id)
            .order_by(PurchaseOrderLine.id)
        )
    )


def _write_lines(db: Session, ctx: TenantContext, po: PurchaseOrder, data: POWrite) -> None:
    for line in _lines(db, po.id):
        db.delete(line)
    db.flush()
    for line in data.lines:
        item = get_item(db, line.item_id)
        if not item.is_active:
            raise ValidationFailed(f"{item.name} is no longer stocked.")
        db.add(
            PurchaseOrderLine(
                organisation_id=ctx.organisation_id,
                purchase_order_id=po.id,
                item_id=item.id,
                quantity_ordered=line.quantity_ordered,
                unit_cost=line.unit_cost.quantize(CENT, ROUND_HALF_UP),
                quantity_received=0,
            )
        )
    db.flush()


def save_po(
    db: Session, ctx: TenantContext, po: PurchaseOrder | None, data: POWrite
) -> PurchaseOrder:
    require_branch(ctx, "inventory.manage", data.branch_id)
    _branch(db, data.branch_id)
    supplier: Supplier = _get(db, Supplier, data.supplier_id, "Supplier")
    if po is None:
        if not supplier.is_active:
            raise ValidationFailed("This supplier is no longer used.")
        po = PurchaseOrder(
            organisation_id=ctx.organisation_id,
            order_number=format_number("PO", next_value(db, ctx.organisation_id, "purchase_order")),
            status="draft",
            created_by=ctx.user_id,
            branch_id=data.branch_id,
            supplier_id=data.supplier_id,
        )
        db.add(po)
        action = "purchase_order.created"
    else:
        require_branch(ctx, "inventory.manage", po.branch_id)
        if po.status != "draft":
            raise Conflict("Only draft purchase orders can be changed.", code="not_draft")
        po.branch_id, po.supplier_id = data.branch_id, data.supplier_id
        action = "purchase_order.updated"
    po.expected_on, po.notes = data.expected_on, data.notes or None
    db.flush()
    _write_lines(db, ctx, po, data)
    ctx.audit(
        db,
        action,
        "purchase_order",
        po.id,
        branch_id=po.branch_id,
        details={"number": po.order_number, "lines": len(data.lines)},
    )
    return po


def place_po(db: Session, ctx: TenantContext, po: PurchaseOrder) -> None:
    require_branch(ctx, "inventory.manage", po.branch_id)
    if po.status != "draft":
        raise Conflict("This purchase order has already been placed.")
    po.status, po.ordered_at = "ordered", datetime.now(UTC)
    ctx.audit(
        db,
        "purchase_order.placed",
        "purchase_order",
        po.id,
        branch_id=po.branch_id,
        details={"number": po.order_number},
    )


def cancel_po(db: Session, ctx: TenantContext, po: PurchaseOrder, reason: str) -> None:
    require_branch(ctx, "inventory.manage", po.branch_id)
    if po.status not in ("draft", "ordered"):
        raise Conflict("Purchase orders with received stock can't be cancelled.")
    po.status, po.cancelled_at, po.cancel_reason = "cancelled", datetime.now(UTC), reason
    ctx.audit(
        db,
        "purchase_order.cancelled",
        "purchase_order",
        po.id,
        branch_id=po.branch_id,
        details={"number": po.order_number},
    )


def receive_po(db: Session, ctx: TenantContext, po: PurchaseOrder, data: POReceipt) -> None:
    require_branch(ctx, "inventory.manage", po.branch_id)
    if po.status not in ("ordered", "partially_received"):
        raise Conflict("Place the order before receiving stock against it.", code="not_ordered")
    lines = {line.id: line for line in _lines(db, po.id)}
    for entry in data.lines:
        line = lines.get(entry.line_id)
        if line is None:
            raise ValidationFailed("A received line is not on this purchase order.")
        if line.quantity_received + entry.quantity > line.quantity_ordered:
            raise Conflict(
                "More received than ordered; receive the extra separately.", code="over_received"
            )
        item = get_item(db, line.item_id)
        _check_batch_details(ctx, item, entry)
        batch = _new_batch(
            db,
            ctx,
            item=item,
            branch_id=po.branch_id,
            quantity=entry.quantity,
            unit_cost=line.unit_cost,
            details=entry,
            supplier_id=po.supplier_id,
            purchase_order_id=po.id,
        )
        _move(
            db, ctx, batch, "receipt", entry.quantity, reference=data.reference or po.order_number
        )
        line.quantity_received += entry.quantity
    db.flush()
    complete = all(line.quantity_received == line.quantity_ordered for line in lines.values())
    po.status = "received" if complete else "partially_received"
    ctx.audit(
        db,
        "purchase_order.received",
        "purchase_order",
        po.id,
        branch_id=po.branch_id,
        details={"number": po.order_number, "lines": len(data.lines), "status": po.status},
    )


def po_reads(db: Session, rows: list[PurchaseOrder]) -> list[PORead]:
    if not rows:
        return []
    ids = [p.id for p in rows]
    lines = list(
        db.scalars(
            select(PurchaseOrderLine)
            .where(PurchaseOrderLine.purchase_order_id.in_(ids))
            .order_by(PurchaseOrderLine.id)
        )
    )
    items = {
        i.id: i
        for i in db.scalars(
            select(InventoryItem).where(InventoryItem.id.in_({line.item_id for line in lines}))
        )
    }
    suppliers = dict(
        db.execute(
            select(Supplier.id, Supplier.name).where(Supplier.id.in_({p.supplier_id for p in rows}))
        ).all()
    )
    branches = dict(
        db.execute(
            select(Branch.id, Branch.name).where(Branch.id.in_({p.branch_id for p in rows}))
        ).all()
    )
    by_po: dict[uuid.UUID, list[POLineRead]] = {}
    for line in lines:
        item = items[line.item_id]
        by_po.setdefault(line.purchase_order_id, []).append(
            POLineRead(
                id=line.id,
                item_id=item.id,
                item_name=item.name,
                sku=item.sku,
                unit=item.unit,
                track_expiry=item.track_expiry,
                quantity_ordered=line.quantity_ordered,
                quantity_received=line.quantity_received,
                unit_cost=line.unit_cost,
                line_total=(line.unit_cost * line.quantity_ordered).quantize(CENT, ROUND_HALF_UP),
            )
        )
    return [
        PORead(
            id=p.id,
            order_number=p.order_number,
            status=p.status,  # type: ignore[arg-type]
            branch_id=p.branch_id,
            branch_name=branches.get(p.branch_id, ""),
            supplier_id=p.supplier_id,
            supplier_name=suppliers.get(p.supplier_id, ""),
            expected_on=p.expected_on,
            notes=p.notes,
            total=sum((ln.line_total for ln in by_po.get(p.id, [])), Decimal("0.00")),
            created_at=p.created_at,
            ordered_at=p.ordered_at,
            cancelled_at=p.cancelled_at,
            cancel_reason=p.cancel_reason,
            lines=by_po.get(p.id, []),
        )
        for p in rows
    ]


def count_movements(db: Session, query) -> int:  # type: ignore[no-untyped-def]
    return db.scalar(select(func.count()).select_from(query.subquery())) or 0
