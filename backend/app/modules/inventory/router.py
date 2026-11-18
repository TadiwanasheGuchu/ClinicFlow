import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import Conflict, NotFound
from app.core.tenancy import TenantContext, require
from app.modules.branches.models import Branch
from app.modules.inventory import service
from app.modules.inventory.models import (
    InventoryItem,
    PurchaseOrder,
    StockBatch,
    StockMovement,
    Supplier,
)
from app.modules.inventory.schemas import (
    Adjustment,
    BatchRead,
    ItemRead,
    ItemStock,
    ItemWrite,
    MovementRead,
    POCancel,
    PORead,
    POReceipt,
    POWrite,
    ReceiptCreate,
    StockOverview,
    SupplierRead,
    SupplierWrite,
    TransferCreate,
    UsageCreate,
)
from app.shared.schemas import Page, PageParams

router = APIRouter(tags=["inventory"])
DB = Annotated[Session, Depends(get_db)]
Reader = Annotated[TenantContext, Depends(require("inventory.read"))]
Manager = Annotated[TenantContext, Depends(require("inventory.manage"))]
Adjuster = Annotated[TenantContext, Depends(require("inventory.adjust"))]
Configurer = Annotated[TenantContext, Depends(require("inventory.adjust", org_wide=True))]


# --- Items and suppliers -----------------------------------------------------------------


def _save(db: Session, ctx: TenantContext, row: InventoryItem | Supplier, action: str) -> None:
    try:
        db.flush()
    except IntegrityError as exc:
        what = (
            "an item with this SKU"
            if isinstance(row, InventoryItem)
            else "a supplier with this name"
        )
        raise Conflict(f"There is already {what}.") from exc
    ctx.audit(db, action, action.split(".")[0], row.id)
    db.commit()


@router.get("/inventory/items", response_model=list[ItemRead])
def list_items(ctx: Reader, db: DB, include_inactive: bool = False) -> object:
    query = select(InventoryItem).order_by(InventoryItem.name)
    if not include_inactive:
        query = query.where(InventoryItem.is_active.is_(True))
    return db.scalars(query).all()


@router.post("/inventory/items", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
def create_item(data: ItemWrite, ctx: Configurer, db: DB) -> object:
    item = InventoryItem(organisation_id=ctx.organisation_id, **data.model_dump())
    db.add(item)
    _save(db, ctx, item, "inventory_item.created")
    return item


@router.put("/inventory/items/{item_id}", response_model=ItemRead)
def update_item(item_id: uuid.UUID, data: ItemWrite, ctx: Configurer, db: DB) -> object:
    item = service.get_item(db, item_id)
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    _save(db, ctx, item, "inventory_item.updated")
    return item


@router.get("/inventory/items/{item_id}", response_model=ItemStock)
def item_stock(item_id: uuid.UUID, ctx: Reader, db: DB, include_empty: bool = False) -> object:
    item = service.get_item(db, item_id)
    query = select(StockBatch).where(StockBatch.item_id == item.id)
    scope = ctx.branch_scope("inventory.read")
    if scope is not None:
        query = query.where(StockBatch.branch_id.in_(scope))
    if not include_empty:
        query = query.where(StockBatch.quantity_remaining > 0)
    rows = list(
        db.scalars(query.order_by(StockBatch.expiry_date.nulls_last(), StockBatch.received_at))
    )
    return ItemStock(item=service.item_read(item), batches=service.batch_reads(db, ctx, rows))


@router.get("/inventory/suppliers", response_model=list[SupplierRead])
def list_suppliers(ctx: Reader, db: DB, include_inactive: bool = False) -> object:
    query = select(Supplier).order_by(Supplier.name)
    if not include_inactive:
        query = query.where(Supplier.is_active.is_(True))
    return db.scalars(query).all()


@router.post(
    "/inventory/suppliers", response_model=SupplierRead, status_code=status.HTTP_201_CREATED
)
def create_supplier(data: SupplierWrite, ctx: Configurer, db: DB) -> object:
    supplier = Supplier(organisation_id=ctx.organisation_id, **data.model_dump())
    db.add(supplier)
    _save(db, ctx, supplier, "supplier.created")
    return supplier


@router.put("/inventory/suppliers/{supplier_id}", response_model=SupplierRead)
def update_supplier(supplier_id: uuid.UUID, data: SupplierWrite, ctx: Configurer, db: DB) -> object:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise NotFound("Supplier not found.")
    for key, value in data.model_dump().items():
        setattr(supplier, key, value)
    _save(db, ctx, supplier, "supplier.updated")
    return supplier


# --- Stock -------------------------------------------------------------------------------


@router.get("/inventory/stock", response_model=StockOverview)
def stock(
    ctx: Reader, db: DB, branch_id: uuid.UUID | None = None, include_empty: bool = False
) -> object:
    return service.overview(db, ctx, branch_id, include_empty)


@router.post("/inventory/receipts", response_model=BatchRead, status_code=status.HTTP_201_CREATED)
def receive(data: ReceiptCreate, ctx: Manager, db: DB) -> object:
    batch = service.receive(db, ctx, data)
    db.commit()
    return service.batch_reads(db, ctx, [batch])[0]


@router.post("/inventory/usage", response_model=list[BatchRead])
def use(data: UsageCreate, ctx: Manager, db: DB) -> object:
    batches = service.use(db, ctx, data)
    db.commit()
    return service.batch_reads(db, ctx, batches)


@router.post("/inventory/batches/{batch_id}/adjust", response_model=BatchRead)
def adjust(batch_id: uuid.UUID, data: Adjustment, ctx: Adjuster, db: DB) -> object:
    batch = service.get_batch(db, ctx, batch_id, lock=True)
    service.adjust(db, ctx, batch, data)
    db.commit()
    return service.batch_reads(db, ctx, [batch])[0]


@router.post("/inventory/batches/{batch_id}/transfer", response_model=BatchRead)
def transfer(batch_id: uuid.UUID, data: TransferCreate, ctx: Manager, db: DB) -> object:
    batch = service.get_batch(db, ctx, batch_id, lock=True)
    arrived = service.transfer(db, ctx, batch, data)
    db.commit()
    return service.batch_reads(db, ctx, [arrived])[0]


@router.get("/inventory/movements", response_model=Page[MovementRead])
def movements(
    ctx: Reader,
    db: DB,
    page: Annotated[PageParams, Depends()],
    item_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    movement_type: Literal["receipt", "usage", "transfer_out", "transfer_in", "count", "write_off"]
    | None = None,
) -> object:
    query = select(StockMovement)
    scope = ctx.branch_scope("inventory.read")
    if scope is not None:
        query = query.where(StockMovement.branch_id.in_(scope))
    for column, value in (
        (StockMovement.item_id, item_id),
        (StockMovement.branch_id, branch_id),
        (StockMovement.movement_type, movement_type),
    ):
        if value is not None:
            query = query.where(column == value)
    total = service.count_movements(db, query)
    rows = list(
        db.scalars(
            query.order_by(StockMovement.occurred_at.desc(), StockMovement.id)
            .limit(page.limit)
            .offset(page.offset)
        )
    )
    items = dict(
        db.execute(
            select(InventoryItem.id, InventoryItem.name).where(
                InventoryItem.id.in_({m.item_id for m in rows})
            )
        ).all()
    )
    branches = dict(
        db.execute(
            select(Branch.id, Branch.name).where(Branch.id.in_({m.branch_id for m in rows}))
        ).all()
    )
    batches = dict(
        db.execute(
            select(StockBatch.id, StockBatch.batch_number).where(
                StockBatch.id.in_({m.batch_id for m in rows})
            )
        ).all()
    )
    names = service.user_names(db, {m.performed_by for m in rows})
    return Page(
        items=[
            MovementRead(
                id=m.id,
                item_id=m.item_id,
                item_name=items.get(m.item_id, ""),
                branch_id=m.branch_id,
                branch_name=branches.get(m.branch_id, ""),
                batch_id=m.batch_id,
                batch_number=batches.get(m.batch_id),
                movement_type=m.movement_type,
                quantity=m.quantity,
                reason=m.reason,
                reference=m.reference,
                performed_by_name=names.get(m.performed_by, ""),
                occurred_at=m.occurred_at,
            )
            for m in rows
        ],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


# --- Purchase orders ---------------------------------------------------------------------


@router.get("/inventory/purchase-orders", response_model=Page[PORead])
def list_pos(
    ctx: Reader,
    db: DB,
    page: Annotated[PageParams, Depends()],
    group: Literal["open", "draft", "closed", "all"] = "open",
) -> object:
    query = select(PurchaseOrder)
    scope = ctx.branch_scope("inventory.read")
    if scope is not None:
        query = query.where(PurchaseOrder.branch_id.in_(scope))
    statuses = {
        "open": ("ordered", "partially_received"),
        "draft": ("draft",),
        "closed": ("received", "cancelled"),
    }.get(group)
    if statuses:
        query = query.where(PurchaseOrder.status.in_(statuses))
    total = service.count_movements(db, query)
    rows = list(
        db.scalars(
            query.order_by(PurchaseOrder.created_at.desc()).limit(page.limit).offset(page.offset)
        )
    )
    return Page(items=service.po_reads(db, rows), total=total, limit=page.limit, offset=page.offset)


@router.post(
    "/inventory/purchase-orders", response_model=PORead, status_code=status.HTTP_201_CREATED
)
def create_po(data: POWrite, ctx: Manager, db: DB) -> object:
    po = service.save_po(db, ctx, None, data)
    db.commit()
    return service.po_reads(db, [po])[0]


@router.get("/inventory/purchase-orders/{po_id}", response_model=PORead)
def read_po(po_id: uuid.UUID, ctx: Reader, db: DB) -> object:
    return service.po_reads(db, [service.get_po(db, ctx, po_id)])[0]


@router.put("/inventory/purchase-orders/{po_id}", response_model=PORead)
def update_po(po_id: uuid.UUID, data: POWrite, ctx: Manager, db: DB) -> object:
    po = service.save_po(db, ctx, service.get_po(db, ctx, po_id, lock=True), data)
    db.commit()
    return service.po_reads(db, [po])[0]


@router.post("/inventory/purchase-orders/{po_id}/place", response_model=PORead)
def place_po(po_id: uuid.UUID, ctx: Manager, db: DB) -> object:
    po = service.get_po(db, ctx, po_id, lock=True)
    service.place_po(db, ctx, po)
    db.commit()
    return service.po_reads(db, [po])[0]


@router.post("/inventory/purchase-orders/{po_id}/receive", response_model=PORead)
def receive_po(po_id: uuid.UUID, data: POReceipt, ctx: Manager, db: DB) -> object:
    po = service.get_po(db, ctx, po_id, lock=True)
    service.receive_po(db, ctx, po, data)
    db.commit()
    return service.po_reads(db, [po])[0]


@router.post("/inventory/purchase-orders/{po_id}/cancel", response_model=PORead)
def cancel_po(po_id: uuid.UUID, data: POCancel, ctx: Manager, db: DB) -> object:
    po = service.get_po(db, ctx, po_id, lock=True)
    service.cancel_po(db, ctx, po, data.reason)
    db.commit()
    return service.po_reads(db, [po])[0]
