import uuid
from datetime import date
from decimal import Decimal

from app.shared.schemas import Schema


class DayCounts(Schema):
    date: date
    booked: int
    completed: int
    cancelled: int
    no_show: int
    walk_in: int
    online: int


class ProviderUtilisation(Schema):
    provider_id: uuid.UUID
    provider_name: str
    booked: int
    completed: int
    no_show: int
    booked_minutes: int
    available_minutes: int
    utilisation_percent: Decimal | None


class BranchCounts(Schema):
    branch_id: uuid.UUID
    branch_name: str
    booked: int
    completed: int
    cancelled: int
    no_show: int


class OperationalReport(Schema):
    start: date
    end: date
    branch_id: uuid.UUID | None
    totals: DayCounts
    cancellation_rate_percent: Decimal | None
    no_show_rate_percent: Decimal | None
    average_wait_minutes: Decimal | None
    wait_sample: int
    new_patients: int
    consultations: int
    daily: list[DayCounts]
    by_provider: list[ProviderUtilisation]
    by_branch: list[BranchCounts]


class MoneyByKey(Schema):
    key: str
    label: str
    count: int
    amount: Decimal


class PeriodMoney(Schema):
    period: str  # YYYY-MM-DD or YYYY-MM
    invoiced: Decimal
    collected: Decimal
    refunded: Decimal


class AgedDebt(Schema):
    bucket: str
    invoices: int
    amount: Decimal


class ClaimSummary(Schema):
    status: str
    count: int
    claimed: Decimal
    paid: Decimal


class FinancialReport(Schema):
    start: date
    end: date
    branch_id: uuid.UUID | None
    invoiced: Decimal
    invoice_count: int
    credited: Decimal
    collected: Decimal
    refunded: Decimal
    net_collected: Decimal
    series: list[PeriodMoney]
    collected_by_method: list[MoneyByKey]
    revenue_by_service: list[MoneyByKey]
    revenue_by_provider: list[MoneyByKey]
    outstanding_total: Decimal
    aged_debt: list[AgedDebt]
    claims: list[ClaimSummary]
    claims_outstanding: Decimal
    claim_rejection_rate_percent: Decimal | None
