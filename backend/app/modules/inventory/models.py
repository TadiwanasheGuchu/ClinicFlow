"""Inventory: items, suppliers, stock batches per branch, an append-only movement ledger and
purchase orders.

Stock levels are never edited directly. Every change is a row in ``stock_movements``; a
database trigger (migration 0007) applies it to the batch, and ``quantity_remaining >= 0``
makes negative stock impossible. Quantities are whole units of the item's unit of measure.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey

MOVEMENT_TYPES = (
    "receipt",
    "usage",
    "transfer_out",
    "transfer_in",
    "count",
    "write_off",
)
Money = Numeric(12, 2)
PO_STATUSES = ("draft", "ordered", "partially_received", "received", "cancelled")


def _same_org(column: str, target: str, name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organisation_id", column], [f"{target}.organisation_id", f"{target}.id"], name=name
    )


class InventoryItem(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "inventory_items"
    __table_args__ = (
        UniqueConstraint("organisation_id", "sku"),
        UniqueConstraint("organisation_id", "id", name="uq_inventory_items_org_id"),
        CheckConstraint("reorder_level >= 0", name="ck_item_reorder_level"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    sku: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(100))
    unit: Mapped[str] = mapped_column(String(30))  # tablet, box, ml, each, ...
    # Reorder when on-hand stock at a branch falls to this level or below.
    reorder_level: Mapped[int] = mapped_column(Integer, default=0)
    # Medicines and anything perishable: receipts need a batch number and expiry date.
    track_expiry: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Supplier(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("organisation_id", "name"),
        UniqueConstraint("organisation_id", "id", name="uq_suppliers_org_id"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    contact_person: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(254))
    address: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PurchaseOrder(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("organisation_id", "order_number"),
        UniqueConstraint("organisation_id", "id", name="uq_purchase_orders_org_id"),
        _same_org("supplier_id", "suppliers", "fk_po_supplier_same_org"),
        _same_org("branch_id", "branches", "fk_po_branch_same_org"),
        CheckConstraint(
            "status IN ('draft','ordered','partially_received','received','cancelled')",
            name="ck_po_status",
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    branch_id: Mapped[uuid.UUID] = mapped_column(index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column()
    order_number: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    expected_on: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    ordered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(Text)


class PurchaseOrderLine(UUIDPrimaryKey, Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        UniqueConstraint("organisation_id", "id", name="uq_po_lines_org_id"),
        _same_org("purchase_order_id", "purchase_orders", "fk_po_lines_po_same_org"),
        _same_org("item_id", "inventory_items", "fk_po_lines_item_same_org"),
        CheckConstraint("quantity_ordered > 0", name="ck_po_line_qty"),
        CheckConstraint("unit_cost >= 0", name="ck_po_line_cost"),
        CheckConstraint(
            "quantity_received >= 0 AND quantity_received <= quantity_ordered",
            name="ck_po_line_received",
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(index=True)
    item_id: Mapped[uuid.UUID] = mapped_column()
    quantity_ordered: Mapped[int] = mapped_column(Integer)
    unit_cost: Mapped[Decimal] = mapped_column(Money)
    quantity_received: Mapped[int] = mapped_column(Integer, default=0)


class StockBatch(UUIDPrimaryKey, Timestamps, Base):
    """Stock of one item at one branch from one delivery (or transfer)."""

    __tablename__ = "stock_batches"
    __table_args__ = (
        UniqueConstraint("organisation_id", "id", name="uq_stock_batches_org_id"),
        _same_org("item_id", "inventory_items", "fk_batches_item_same_org"),
        _same_org("branch_id", "branches", "fk_batches_branch_same_org"),
        _same_org("supplier_id", "suppliers", "fk_batches_supplier_same_org"),
        _same_org("purchase_order_id", "purchase_orders", "fk_batches_po_same_org"),
        CheckConstraint("quantity_received > 0", name="ck_batch_received"),
        CheckConstraint("quantity_remaining >= 0", name="ck_batch_not_negative"),
        CheckConstraint("unit_cost >= 0", name="ck_batch_cost"),
        Index("ix_batches_org_item_branch", "organisation_id", "item_id", "branch_id"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    item_id: Mapped[uuid.UUID] = mapped_column()
    branch_id: Mapped[uuid.UUID] = mapped_column()
    batch_number: Mapped[str | None] = mapped_column(String(60))
    expiry_date: Mapped[date | None] = mapped_column(Date)
    unit_cost: Mapped[Decimal] = mapped_column(Money)
    quantity_received: Mapped[int] = mapped_column(Integer)
    # Maintained only by the stock_movements trigger.
    quantity_remaining: Mapped[int] = mapped_column(Integer, default=0)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column()
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column()
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StockMovement(UUIDPrimaryKey, Base):
    """Append-only ledger. ``quantity`` is signed: positive adds stock, negative removes it."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        _same_org("batch_id", "stock_batches", "fk_movements_batch_same_org"),
        CheckConstraint("quantity <> 0", name="ck_movement_nonzero"),
        CheckConstraint(
            "movement_type IN ('receipt','usage','transfer_out','transfer_in','count','write_off')",
            name="ck_movement_type",
        ),
        CheckConstraint(
            "(movement_type IN ('receipt','transfer_in') AND quantity > 0)"
            " OR (movement_type IN ('usage','transfer_out','write_off') AND quantity < 0)"
            " OR movement_type = 'count'",
            name="ck_movement_sign",
        ),
        Index("ix_movements_org_item_time", "organisation_id", "item_id", "occurred_at"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    branch_id: Mapped[uuid.UUID] = mapped_column(index=True)
    item_id: Mapped[uuid.UUID] = mapped_column()
    batch_id: Mapped[uuid.UUID] = mapped_column(index=True)
    movement_type: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(Text)
    reference: Mapped[str | None] = mapped_column(String(100))
    # Groups the two halves of a transfer.
    transfer_id: Mapped[uuid.UUID | None] = mapped_column()
    performed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
