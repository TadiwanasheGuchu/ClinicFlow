import uuid
from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import ValidationFailed
from app.core.tenancy import TenantContext, TenantDep, deny, require
from app.modules.branches.models import Branch
from app.modules.members.models import Membership, MembershipRole
from app.modules.roster import service
from app.modules.roster.models import LeaveRequest, Shift
from app.modules.roster.schemas import (
    CopyResult,
    CopyWeek,
    LeaveCreate,
    LeaveDecision,
    LeaveRead,
    LeaveRecord,
    MyRoster,
    Roster,
    ShiftRead,
    ShiftWrite,
    StaffRow,
)
from app.modules.staff.models import StaffProfile

router = APIRouter(tags=["roster"])
DB = Annotated[Session, Depends(get_db)]
Reader = Annotated[TenantContext, Depends(require("roster.read"))]
Manager = Annotated[TenantContext, Depends(require("roster.manage"))]
Days = Annotated[int, Query(ge=1, le=31)]


def _period(ctx: TenantContext, start: date, days: int) -> tuple:  # type: ignore[type-arg]
    return service.day_start(ctx, start), service.day_start(ctx, start + timedelta(days=days))


def _leave_in(query, start: date, end: date):  # type: ignore[no-untyped-def]
    return query.where(
        LeaveRequest.status.in_(("requested", "approved")),
        LeaveRequest.starts_on < end,
        LeaveRequest.ends_on >= start,
    )


@router.get("/roster", response_model=Roster)
def roster(ctx: Reader, db: DB, branch_id: uuid.UUID, start: date, days: Days = 7) -> object:
    service.require_branch(ctx, "roster.read", branch_id)
    period_start, period_end = _period(ctx, start, days)
    shifts = list(
        db.scalars(
            select(Shift)
            .where(
                Shift.branch_id == branch_id,
                Shift.status == "scheduled",
                Shift.starts_at < period_end,
                Shift.ends_at > period_start,
            )
            .order_by(Shift.starts_at)
        )
    )
    # Staff who work in this branch (a role there or organisation-wide), plus anyone rostered.
    members = set(
        db.scalars(
            select(MembershipRole.membership_id)
            .join(Membership, Membership.id == MembershipRole.membership_id)
            .where(
                Membership.status == "active",
                (MembershipRole.branch_id == branch_id) | (MembershipRole.branch_id.is_(None)),
            )
        )
    ) | {s.membership_id for s in shifts}
    profiles = dict(
        db.execute(
            select(StaffProfile.membership_id, StaffProfile.profession).where(
                StaffProfile.membership_id.in_(members)
            )
        ).all()
    )
    who = service.names(db, members)
    end_day = start + timedelta(days=days)
    leave = list(
        db.scalars(
            _leave_in(select(LeaveRequest), start, end_day).where(
                LeaveRequest.membership_id.in_(members)
            )
        )
    )
    hours: dict[str, float] = {}
    for s in shifts:
        overlap = min(s.ends_at, period_end) - max(s.starts_at, period_start)
        hours[str(s.membership_id)] = round(
            hours.get(str(s.membership_id), 0) + overlap.total_seconds() / 3600, 2
        )
    return Roster(
        start=start,
        end=end_day,
        branch_id=branch_id,
        staff=sorted(
            (
                StaffRow(membership_id=m, name=who.get(m, ""), profession=profiles.get(m))
                for m in members
            ),
            key=lambda r: r.name.lower(),
        ),
        shifts=service.shift_reads(db, shifts),
        leave=service.leave_reads(
            db, ctx, leave, detail=ctx.has_in_branch("roster.manage", branch_id)
        ),
        hours=hours,
    )


@router.post("/shifts", response_model=ShiftRead, status_code=status.HTTP_201_CREATED)
def create_shift(data: ShiftWrite, ctx: Manager, db: DB) -> object:
    shift = service.create_shift(db, ctx, data)
    db.commit()
    return service.shift_reads(db, [shift])[0]


@router.put("/shifts/{shift_id}", response_model=ShiftRead)
def update_shift(shift_id: uuid.UUID, data: ShiftWrite, ctx: Manager, db: DB) -> object:
    shift = service.get_shift(db, ctx, shift_id)
    service.update_shift(db, ctx, shift, data)
    db.commit()
    return service.shift_reads(db, [shift])[0]


@router.post("/shifts/{shift_id}/cancel", response_model=ShiftRead)
def cancel_shift(shift_id: uuid.UUID, ctx: Manager, db: DB) -> object:
    shift = service.get_shift(db, ctx, shift_id)
    service.cancel_shift(db, ctx, shift)
    db.commit()
    return service.shift_reads(db, [shift])[0]


@router.post("/shifts/copy-week", response_model=CopyResult)
def copy_week(data: CopyWeek, ctx: Manager, db: DB) -> object:
    created, skipped = service.copy_week(db, ctx, data.branch_id, data.from_start, data.to_start)
    db.commit()
    return CopyResult(created=created, skipped=skipped)


# --- Leave -------------------------------------------------------------------------------


@router.get("/leave", response_model=list[LeaveRead])
def list_leave(
    ctx: Manager,
    db: DB,
    status_filter: Annotated[
        Literal["requested", "upcoming", "all"], Query(alias="status")
    ] = "requested",
) -> object:
    query = select(LeaveRequest)
    if status_filter == "requested":
        query = query.where(LeaveRequest.status == "requested")
    elif status_filter == "upcoming":
        today = service.local_today(ctx)
        query = query.where(LeaveRequest.status == "approved", LeaveRequest.ends_on >= today)
    rows = [
        r
        for r in db.scalars(query.order_by(LeaveRequest.starts_on).limit(200))
        if service.can_manage_member(db, ctx, r.membership_id)
    ]
    return service.leave_reads(db, ctx, rows, detail=True)


@router.post("/leave", response_model=LeaveRead, status_code=status.HTTP_201_CREATED)
def record_leave(data: LeaveRecord, ctx: Manager, db: DB) -> object:
    service.active_member(db, data.membership_id)
    if not service.can_manage_member(db, ctx, data.membership_id):
        raise deny(ctx, "roster.manage", "leave")
    leave = service.request_leave(db, ctx, data.membership_id, data)
    affected = (None, None)
    if data.approve:
        affected = service.decide(db, ctx, leave, "approved", None)
    db.commit()
    read = service.leave_reads(db, ctx, [leave], detail=True)[0]
    read.appointments_affected, read.shifts_affected = affected
    return read


@router.post("/leave/{leave_id}/decide", response_model=LeaveRead)
def decide(leave_id: uuid.UUID, data: LeaveDecision, ctx: Manager, db: DB) -> object:
    leave = service.get_leave(db, leave_id)
    appointments, shifts = service.decide(db, ctx, leave, data.decision, data.note)
    db.commit()
    read = service.leave_reads(db, ctx, [leave], detail=True)[0]
    read.appointments_affected, read.shifts_affected = appointments, shifts
    return read


@router.post("/leave/{leave_id}/cancel", response_model=LeaveRead)
def cancel_leave(leave_id: uuid.UUID, ctx: TenantDep, db: DB) -> object:
    leave = service.get_leave(db, leave_id)
    service.cancel_leave(db, ctx, leave)
    db.commit()
    return service.leave_reads(db, ctx, [leave], detail=True)[0]


# --- Own roster and leave (every active staff member) --------------------------------


@router.get("/me/roster", response_model=MyRoster)
def my_roster(ctx: TenantDep, db: DB, start: date, days: Days = 14) -> object:
    me = ctx.membership.id
    period_start, period_end = _period(ctx, start, days)
    shifts = list(
        db.scalars(
            select(Shift)
            .where(
                Shift.membership_id == me,
                Shift.status == "scheduled",
                Shift.starts_at < period_end,
                Shift.ends_at > period_start,
            )
            .order_by(Shift.starts_at)
        )
    )
    leave = list(
        db.scalars(
            select(LeaveRequest)
            .where(
                LeaveRequest.membership_id == me,
                LeaveRequest.ends_on >= start - timedelta(days=90),
            )
            .order_by(LeaveRequest.starts_on.desc())
        )
    )
    branches = dict(
        db.execute(
            select(Branch.id, Branch.name).where(Branch.id.in_({s.branch_id for s in shifts}))
        ).all()
    )
    return MyRoster(
        start=start,
        end=start + timedelta(days=days),
        membership_id=me,
        shifts=service.shift_reads(db, shifts),
        leave=service.leave_reads(db, ctx, leave, detail=True),
        branch_names={str(k): v for k, v in branches.items()},
    )


@router.post("/me/leave", response_model=LeaveRead, status_code=status.HTTP_201_CREATED)
def request_leave(data: LeaveCreate, ctx: TenantDep, db: DB) -> object:
    if data.ends_on < service.local_today(ctx) - timedelta(days=30):
        raise ValidationFailed("Ask a manager to record leave from more than a month ago.")
    leave = service.request_leave(db, ctx, ctx.membership.id, data)
    db.commit()
    return service.leave_reads(db, ctx, [leave], detail=True)[0]
