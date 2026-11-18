import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import EmailStr, Field

from app.shared.schemas import Schema

Quantity = Field(gt=0, le=1_000_000)
Cost = Field(ge=0, le=Decimal("9999999.99"), decimal_places=2)


class ItemWrite(Schema):
    sku: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=2, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    unit: str = Field(min_length=1, max_length=30)
    reorder_level: int = Field(default=0, ge=0, le=1_000_000)
    track_expiry: bool = False
    is_active: bool = True


class ItemRead(ItemWrite):
    id: uuid.UUID


class SupplierWrite(Schema):
    name: str = Field(min_length=2, max_length=200)
    contact_person: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    address: str | None = Field(default=None, max_length=1000)
    is_active: bool = True


class SupplierRead(SupplierWrite):
    id: uuid.UUID
    email: str | None = None  # type: ignore[assignment]


class BatchDetails(Schema):
    batch_number: str | None = Field(default=None, max_length=60)
    expiry_date: date | None = None


class ReceiptCreate(BatchDetails):
    branch_id: uuid.UUID
    item_id: uuid.UUID
    quantity: int = Quantity
    unit_cost: Decimal = Cost
    supplier_id: uuid.UUID | None = None
    reference: str | None = Field(default=None, max_length=100)


class UsageCreate(Schema):
    branch_id: uuid.UUID
    item_id: uuid.UUID
    quantity: int = Quantity
    reason: str | None = Field(default=None, max_length=500)
    reference: str | None = Field(default=None, max_length=100)


class Adjustment(Schema):
    """``count``: the quantity physically counted. ``write_off``: the quantity removed."""

    kind: Literal["count", "write_off"]
    quantity: int = Field(ge=0, le=1_000_000)
    reason: str = Field(min_length=3, max_length=500)


class TransferCreate(Schema):
    to_branch_id: uuid.UUID
    quantity: int = Quantity
    reason: str | None = Field(default=None, max_length=500)


class BatchRead(Schema):
    id: uuid.UUID
    item_id: uuid.UUID
    branch_id: uuid.UUID
    batch_number: str | None
    expiry_date: date | None
    unit_cost: Decimal
    quantity_received: int
    quantity_remaining: int
    received_at: datetime
    supplier_name: str | None
    expired: bool


class MovementRead(Schema):
    id: uuid.UUID
    item_id: uuid.UUID
    item_name: str
    branch_id: uuid.UUID
    branch_name: str
    batch_id: uuid.UUID
    batch_number: str | None
    movement_type: str
    quantity: int
    reason: str | None
    reference: str | None
    performed_by_name: str
    occurred_at: datetime


class StockLevel(Schema):
    item_id: uuid.UUID
    sku: str
    name: str
    category: str | None
    unit: str
    reorder_level: int
    branch_id: uuid.UUID
    branch_name: str
    on_hand: int
    usable: int  # excludes expired stock
    expired: int
    expiring_soon: int
    next_expiry: date | None
    value: Decimal
    below_reorder: bool


class StockOverview(Schema):
    levels: list[StockLevel]
    total_value: Decimal
    expiry_window_days: int


class ItemStock(Schema):
    item: ItemRead
    batches: list[BatchRead]


# --- Purchase orders ---------------------------------------------------------------------


class POLineWrite(Schema):
    item_id: uuid.UUID
    quantity_ordered: int = Quantity
    unit_cost: Decimal = Cost


class POWrite(Schema):
    branch_id: uuid.UUID
    supplier_id: uuid.UUID
    expected_on: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[POLineWrite] = Field(min_length=1, max_length=100)


class POLineRead(Schema):
    id: uuid.UUID
    item_id: uuid.UUID
    item_name: str
    sku: str
    unit: str
    track_expiry: bool
    quantity_ordered: int
    quantity_received: int
    unit_cost: Decimal
    line_total: Decimal


class PORead(Schema):
    id: uuid.UUID
    order_number: str
    status: Literal["draft", "ordered", "partially_received", "received", "cancelled"]
    branch_id: uuid.UUID
    branch_name: str
    supplier_id: uuid.UUID
    supplier_name: str
    expected_on: date | None
    notes: str | None
    total: Decimal
    created_at: datetime
    ordered_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    lines: list[POLineRead]


class POReceiptLine(BatchDetails):
    line_id: uuid.UUID
    quantity: int = Quantity


class POReceipt(Schema):
    lines: list[POReceiptLine] = Field(min_length=1, max_length=100)
    reference: str | None = Field(default=None, max_length=100)


class POCancel(Schema):
    reason: str = Field(min_length=3, max_length=500)
