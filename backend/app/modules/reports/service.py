"""Operational and financial reports. Aggregates only — no clinical content and no
patient-identifying detail leaves these queries. Dates are local calendar days in the
organisation's timezone; ranges are inclusive of both ends."""

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.appointments.models import Appointment, AppointmentEvent
from app.modules.billing.models import CreditNote, Invoice, InvoiceItem, Payment, Refund
from app.modules.branches.models import Branch
from app.modules.clinical.models import Encounter
from app.modules.medical_aid.models import ClaimEvent, MedicalAidClaim
from app.modules.patients.models import Patient
from app.modules.reports.schemas import (
    AgedDebt,
    BranchCounts,
    ClaimSummary,
    DayCounts,
    FinancialReport,
    MoneyByKey,
    OperationalReport,
    PeriodMoney,
    ProviderUtilisation,
)
from app.modules.scheduling.models import Provider, ProviderAvailability

ZERO = Decimal("0.00")
BOOKED = (
    "requested",
    "pending_confirmation",
    "confirmed",
    "checked_in",
    "waiting",
    "in_consultation",
    "completed",
    "cancelled",
    "no_show",
)
OCCUPYING = (
    "requested",
    "pending_confirmation",
    "confirmed",
    "checked_in",
    "waiting",
    "in_consultation",
    "completed",
)


def pct(numerator: int | Decimal, denominator: int | Decimal) -> Decimal | None:
    if not denominator:
        return None
    return (Decimal(numerator) * 100 / Decimal(denominator)).quantize(Decimal("0.1"), ROUND_HALF_UP)


def bounds(start: date, end: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    return (
        datetime.combine(start, time.min, tzinfo=tz),
        datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz),
    )


def _scope(
    query: Select, column, branch_id: uuid.UUID | None, scope: set[uuid.UUID] | None
) -> Select:  # type: ignore[no-untyped-def]
    if branch_id is not None:
        return query.where(column == branch_id)
    if scope is not None:
        return query.where(column.in_(scope))
    return query


def operational(
    db: Session,
    *,
    start: date,
    end: date,
    tz: ZoneInfo,
    branch_id: uuid.UUID | None,
    scope: set[uuid.UUID] | None,
) -> OperationalReport:
    lo, hi = bounds(start, end, tz)
    appts = list(
        db.scalars(
            _scope(
                select(Appointment).where(Appointment.start_at >= lo, Appointment.start_at < hi),
                Appointment.branch_id,
                branch_id,
                scope,
            )
        )
    )

    def counts(rows: list[Appointment], day: date) -> DayCounts:
        return DayCounts(
            date=day,
            booked=len(rows),
            completed=sum(a.status == "completed" for a in rows),
            cancelled=sum(a.status == "cancelled" for a in rows),
            no_show=sum(a.status == "no_show" for a in rows),
            walk_in=sum(a.booking_source == "walk_in" for a in rows),
            online=sum(a.booking_source == "online" for a in rows),
        )

    by_day: dict[date, list[Appointment]] = defaultdict(list)
    for a in appts:
        by_day[a.start_at.astimezone(tz).date()].append(a)
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    daily = [counts(by_day.get(d, []), d) for d in days]
    totals = counts(appts, start)

    # Waiting: time from check-in to consultation start, from the appointment history.
    ids = [a.id for a in appts]
    waits: list[float] = []
    if ids:
        events = db.execute(
            select(
                AppointmentEvent.appointment_id,
                AppointmentEvent.new_status,
                AppointmentEvent.created_at,
            )
            .where(
                AppointmentEvent.appointment_id.in_(ids),
                AppointmentEvent.new_status.in_(("checked_in", "in_consultation")),
            )
            .order_by(AppointmentEvent.created_at)
        ).all()
        checked: dict[uuid.UUID, datetime] = {}
        seen: set[uuid.UUID] = set()
        for appointment_id, status, at in events:
            if status == "checked_in":
                checked.setdefault(appointment_id, at)
            elif appointment_id in checked and appointment_id not in seen:
                waits.append((at - checked[appointment_id]).total_seconds() / 60)
                seen.add(appointment_id)
    average_wait = (
        Decimal(sum(waits) / len(waits)).quantize(Decimal("0.1"), ROUND_HALF_UP) if waits else None
    )

    # Utilisation: occupied minutes (incl. buffers' absence) over scheduled working minutes.
    providers = {p.id: p for p in db.scalars(select(Provider))}
    windows = list(
        db.scalars(
            _scope(select(ProviderAvailability), ProviderAvailability.branch_id, branch_id, scope)
        )
    )
    available: dict[uuid.UUID, int] = defaultdict(int)
    for d in days:
        for w in windows:
            if w.weekday != d.weekday():
                continue
            if (w.effective_from and d < w.effective_from) or (
                w.effective_until and d > w.effective_until
            ):
                continue
            minutes = (
                datetime.combine(d, w.end_time) - datetime.combine(d, w.start_time)
            ).seconds // 60
            available[w.provider_id] += minutes
    by_provider_rows: dict[uuid.UUID, list[Appointment]] = defaultdict(list)
    for a in appts:
        by_provider_rows[a.provider_id].append(a)
    by_provider = []
    for provider_id in sorted(
        set(by_provider_rows) | set(available),
        key=lambda p: providers[p].display_name if p in providers else "",
    ):
        rows = by_provider_rows.get(provider_id, [])
        booked_minutes = sum(
            int((a.end_at - a.start_at).total_seconds() // 60)
            for a in rows
            if a.status in OCCUPYING
        )
        by_provider.append(
            ProviderUtilisation(
                provider_id=provider_id,
                provider_name=providers[provider_id].display_name
                if provider_id in providers
                else "Unknown",
                booked=len(rows),
                completed=sum(a.status == "completed" for a in rows),
                no_show=sum(a.status == "no_show" for a in rows),
                booked_minutes=booked_minutes,
                available_minutes=available.get(provider_id, 0),
                utilisation_percent=pct(booked_minutes, available.get(provider_id, 0)),
            )
        )

    branches = {b.id: b.name for b in db.scalars(select(Branch))}
    by_branch_rows: dict[uuid.UUID, list[Appointment]] = defaultdict(list)
    for a in appts:
        by_branch_rows[a.branch_id].append(a)
    by_branch = [
        BranchCounts(
            branch_id=b,
            branch_name=branches.get(b, ""),
            booked=len(rows),
            completed=sum(a.status == "completed" for a in rows),
            cancelled=sum(a.status == "cancelled" for a in rows),
            no_show=sum(a.status == "no_show" for a in rows),
        )
        for b, rows in sorted(by_branch_rows.items(), key=lambda kv: branches.get(kv[0], ""))
    ]

    new_patients = (
        db.scalar(
            select(func.count())
            .select_from(Patient)
            .where(Patient.created_at >= lo, Patient.created_at < hi)
        )
        or 0
    )
    consultations = (
        db.scalar(
            _scope(
                select(func.count())
                .select_from(Encounter)
                .where(Encounter.started_at >= lo, Encounter.started_at < hi),
                Encounter.branch_id,
                branch_id,
                scope,
            )
        )
        or 0
    )
    attended_or_missed = totals.completed + totals.no_show
    return OperationalReport(
        start=start,
        end=end,
        branch_id=branch_id,
        totals=totals,
        cancellation_rate_percent=pct(totals.cancelled, totals.booked),
        no_show_rate_percent=pct(totals.no_show, attended_or_missed),
        average_wait_minutes=average_wait,
        wait_sample=len(waits),
        new_patients=new_patients,
        consultations=consultations,
        daily=daily,
        by_provider=by_provider,
        by_branch=by_branch,
    )


def financial(
    db: Session,
    *,
    start: date,
    end: date,
    tz: ZoneInfo,
    branch_id: uuid.UUID | None,
    scope: set[uuid.UUID] | None,
) -> FinancialReport:
    lo, hi = bounds(start, end, tz)
    monthly = (end - start).days > 62

    def period(at: datetime) -> str:
        local = at.astimezone(tz).date()
        return local.strftime("%Y-%m") if monthly else local.isoformat()

    issued = list(
        db.scalars(
            _scope(
                select(Invoice).where(
                    Invoice.status != "draft", Invoice.issued_at >= lo, Invoice.issued_at < hi
                ),
                Invoice.branch_id,
                branch_id,
                scope,
            )
        )
    )
    payments = list(
        db.scalars(
            _scope(
                select(Payment).where(
                    Payment.status == "completed",
                    Payment.received_at >= lo,
                    Payment.received_at < hi,
                ),
                Payment.branch_id,
                branch_id,
                scope,
            )
        )
    )
    refunds = list(
        db.scalars(
            _scope(
                select(Refund).where(Refund.refunded_at >= lo, Refund.refunded_at < hi),
                Refund.branch_id,
                branch_id,
                scope,
            )
        )
    )
    credited = (
        db.scalar(
            _scope(
                select(func.coalesce(func.sum(CreditNote.amount), 0))
                .join(Invoice, Invoice.id == CreditNote.invoice_id)
                .where(CreditNote.issued_at >= lo, CreditNote.issued_at < hi),
                Invoice.branch_id,
                branch_id,
                scope,
            )
        )
        or ZERO
    )

    series: dict[str, PeriodMoney] = {}

    def bucket(key: str) -> PeriodMoney:
        return series.setdefault(
            key, PeriodMoney(period=key, invoiced=ZERO, collected=ZERO, refunded=ZERO)
        )

    for i in issued:
        bucket(period(i.issued_at)).invoiced += i.total  # type: ignore[arg-type]
    for p in payments:
        bucket(period(p.received_at)).collected += p.amount
    for r in refunds:
        bucket(period(r.refunded_at)).refunded += r.amount

    by_method: dict[str, MoneyByKey] = {}
    for p in payments:
        m = by_method.setdefault(
            p.method, MoneyByKey(key=p.method, label=p.method, count=0, amount=ZERO)
        )
        m.count += 1
        m.amount += p.amount

    by_service: dict[str, MoneyByKey] = {}
    issued_ids = [i.id for i in issued]
    if issued_ids:
        for item in db.scalars(select(InvoiceItem).where(InvoiceItem.invoice_id.in_(issued_ids))):
            key = item.code or item.description
            s = by_service.setdefault(
                key, MoneyByKey(key=key, label=item.description, count=0, amount=ZERO)
            )
            s.count += 1
            s.amount += item.line_total

    providers = {p.id: p.display_name for p in db.scalars(select(Provider))}
    appointment_provider = (
        dict(
            db.execute(
                select(Appointment.id, Appointment.provider_id).where(
                    Appointment.id.in_([i.appointment_id for i in issued if i.appointment_id])
                )
            ).all()
        )
        if issued
        else {}
    )
    by_provider: dict[str, MoneyByKey] = {}
    for i in issued:
        pid = appointment_provider.get(i.appointment_id) if i.appointment_id else None
        key = str(pid) if pid else "none"
        label = (
            providers.get(pid, "Not linked to an appointment")
            if pid
            else "Not linked to an appointment"
        )
        row = by_provider.setdefault(key, MoneyByKey(key=key, label=label, count=0, amount=ZERO))
        row.count += 1
        row.amount += i.total

    # Aged debt as of today, by days past due date.
    now = datetime.now(UTC)
    open_invoices = list(
        db.scalars(
            _scope(
                select(Invoice).where(Invoice.status.in_(("issued", "partially_paid"))),
                Invoice.branch_id,
                branch_id,
                scope,
            )
        )
    )
    # Stable codes; the UI supplies the wording.
    codes = ("not_due", "1_30", "31_60", "61_90", "over_90")
    buckets = {c: AgedDebt(bucket=c, invoices=0, amount=ZERO) for c in codes}
    outstanding_total = ZERO
    for i in open_invoices:
        due = i.total - i.amount_credited - (i.amount_paid - i.amount_refunded)
        if due <= 0:
            continue
        overdue = (now - i.due_at).days if i.due_at else 0
        limits = ((0, "not_due"), (30, "1_30"), (60, "31_60"), (90, "61_90"))
        name = next((code for limit, code in limits if overdue <= limit), "over_90")
        buckets[name].invoices += 1
        buckets[name].amount += due
        outstanding_total += due

    # Claims (by the claimed invoice's branch).
    claim_query = select(MedicalAidClaim).join(Invoice, Invoice.id == MedicalAidClaim.invoice_id)
    claims = list(db.scalars(_scope(claim_query, Invoice.branch_id, branch_id, scope)))
    by_status: dict[str, ClaimSummary] = {}
    for c in claims:
        s = by_status.setdefault(
            c.status, ClaimSummary(status=c.status, count=0, claimed=ZERO, paid=ZERO)
        )
        s.count += 1
        s.claimed += c.claimed_amount
        s.paid += c.paid_amount
    waiting = {"submitted", "processing", "accepted", "partially_paid"}
    claims_outstanding = sum(
        (c.claimed_amount - c.paid_amount for c in claims if c.status in waiting), ZERO
    )
    claim_ids = [c.id for c in claims]
    responses = (
        db.execute(
            select(ClaimEvent.new_status, func.count())
            .where(
                ClaimEvent.claim_id.in_(claim_ids),
                ClaimEvent.event_type == "status_changed",
                ClaimEvent.new_status.in_(("accepted", "rejected")),
                ClaimEvent.created_at >= lo,
                ClaimEvent.created_at < hi,
            )
            .group_by(ClaimEvent.new_status)
        ).all()
        if claim_ids
        else []
    )
    response_counts = dict(responses)
    rejected = response_counts.get("rejected", 0)

    invoiced = sum((i.total for i in issued), ZERO)
    collected = sum((p.amount for p in payments), ZERO)
    refunded = sum((r.amount for r in refunds), ZERO)
    return FinancialReport(
        start=start,
        end=end,
        branch_id=branch_id,
        invoiced=invoiced,
        invoice_count=len(issued),
        credited=Decimal(credited),
        collected=collected,
        refunded=refunded,
        net_collected=collected - refunded,
        series=[series[k] for k in sorted(series)],
        collected_by_method=sorted(by_method.values(), key=lambda m: -m.amount),
        revenue_by_service=sorted(by_service.values(), key=lambda m: -m.amount),
        revenue_by_provider=sorted(by_provider.values(), key=lambda m: -m.amount),
        outstanding_total=outstanding_total,
        aged_debt=list(buckets.values()),
        claims=sorted(by_status.values(), key=lambda s: s.status),
        claims_outstanding=claims_outstanding,
        claim_rejection_rate_percent=pct(rejected, rejected + response_counts.get("accepted", 0)),
    )
