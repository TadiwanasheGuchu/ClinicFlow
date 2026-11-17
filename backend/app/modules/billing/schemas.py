import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from app.shared.schemas import Schema

TaxCategory = Literal["standard", "zero", "exempt"]
PaymentMethod = Literal["cash", "card", "eft", "mobile"]
MoneyField = Field(ge=0, max_digits=12, decimal_places=2)


class ServiceWrite(Schema):
    code: str = Field(min_length=1, max_length=30, pattern=r"^[A-Za-z0-9._-]+$")
    tariff_code: str | None = Field(None, max_length=30)
    name: str = Field(min_length=2, max_length=200)
    description: str | None = Field(None, max_length=1000)
    unit_price: Decimal = MoneyField
    tax_category: TaxCategory = "standard"
    is_active: bool = True


class ServiceRead(ServiceWrite):
    id: uuid.UUID


class ItemInput(Schema):
    service_id: uuid.UUID | None = None
    description: str | None = Field(None, min_length=2, max_length=300)
    quantity: Decimal = Field(Decimal("1"), gt=0, max_digits=10, decimal_places=2)
    unit_price: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)
    tax_category: TaxCategory | None = None

    @model_validator(mode="after")
    def _service_or_text(self) -> "ItemInput":
        if self.service_id is None and (self.description is None or self.unit_price is None):
            raise ValueError("Choose a service, or give a description and unit price.")
        return self


class InvoiceCreate(Schema):
    patient_id: uuid.UUID
    branch_id: uuid.UUID | None = None
    appointment_id: uuid.UUID | None = None
    items: list[ItemInput] = Field(default_factory=list, max_length=50)
    notes: str | None = Field(None, max_length=1000)

    @model_validator(mode="after")
    def _branch(self) -> "InvoiceCreate":
        if self.branch_id is None and self.appointment_id is None:
            raise ValueError("Provide branch_id or appointment_id.")
        return self


class InvoiceItemsReplace(Schema):
    items: list[ItemInput] = Field(max_length=50)
    notes: str | None = Field(None, max_length=1000)


class ItemRead(Schema):
    position: int
    service_id: uuid.UUID | None
    code: str | None
    tariff_code: str | None
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    line_subtotal: Decimal
    tax_amount: Decimal
    line_total: Decimal


class PaymentInput(Schema):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    method: PaymentMethod
    reference: str | None = Field(None, max_length=100)


class PaymentRead(Schema):
    id: uuid.UUID
    invoice_id: uuid.UUID
    receipt_number: str
    amount: Decimal
    method: str
    reference: str | None
    status: str
    received_at: datetime
    received_by: uuid.UUID
    claim_id: uuid.UUID | None
    reversed_at: datetime | None
    reversal_reason: str | None


class Reason(Schema):
    reason: str = Field(min_length=3, max_length=500)


class CreditInput(Reason):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class RefundInput(CreditInput):
    method: PaymentMethod
    reference: str | None = Field(None, max_length=100)


class CreditNoteRead(Schema):
    id: uuid.UUID
    credit_note_number: str
    amount: Decimal
    reason: str
    issued_at: datetime
    issued_by: uuid.UUID


class RefundRead(Schema):
    id: uuid.UUID
    refund_number: str
    amount: Decimal
    method: str
    reference: str | None
    reason: str
    refunded_at: datetime
    refunded_by: uuid.UUID


class InvoiceSummary(Schema):
    id: uuid.UUID
    invoice_number: str | None
    status: str
    patient_id: uuid.UUID
    patient_name: str
    patient_number: str
    branch_id: uuid.UUID
    appointment_id: uuid.UUID | None
    total: Decimal
    amount_due: Decimal
    issued_at: datetime | None
    due_at: datetime | None
    created_at: datetime


class InvoiceRead(InvoiceSummary):
    subtotal: Decimal
    tax_amount: Decimal
    amount_paid: Decimal
    amount_credited: Decimal
    amount_refunded: Decimal
    credit_balance: Decimal
    notes: str | None
    items: list[ItemRead]
    payments: list[PaymentRead]
    credit_notes: list[CreditNoteRead]
    refunds: list[RefundRead]
    claims: list[dict]


class StatementLine(Schema):
    date: datetime
    kind: Literal["invoice", "payment", "credit_note", "refund", "payment_reversed"]
    reference: str
    description: str
    debit: Decimal
    credit: Decimal
    balance: Decimal


class Statement(Schema):
    patient_id: uuid.UUID
    lines: list[StatementLine]
    balance: Decimal


class CashUpMethod(Schema):
    method: str
    count: int
    received: Decimal
    refunded: Decimal
    net: Decimal


class CashUp(Schema):
    date: str
    branch_id: uuid.UUID | None
    by_method: list[CashUpMethod]
    total_received: Decimal
    total_refunded: Decimal
    net: Decimal
    reversed_payments: list[PaymentRead]
    payments: list[PaymentRead]
