"""Staff rostering service.

Permissions:
  roster.read    see the roster (shifts and who is away, without leave type or reason)
  roster.manage  plan shifts in a branch; decide or record leave for staff whose roles are
                 in a branch where the manager holds roster.manage (anyone, if held
                 organisation-wide; staff with organisation-wide roles need such a manager)
Every active staff member can see their own shifts and request or cancel their own leave.
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from psycopg.errors import ExclusionViolation
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.tenancy import TenantContext, deny
from app.modules.appointments.models import Appointment
from app.modules.members.models import Membership, MembershipRole
from app.modules.roster.models import LeaveRequest, Shift
from app.modules.roster.schemas import LeaveCreate, LeaveRead, ShiftRead, ShiftWrite
from app.modules.scheduling.models import Provider, ProviderUnavailability
from app.modules.staff.models import StaffProfile
from app.modules.users.models import User

FINISHED_APPOINTMENTS = ("cancelled", "no_show", "completed")


def tz(ctx: TenantContext) -> ZoneInfo:
    return ZoneInfo(ctx.organisation.timezone)


def local_today(ctx: TenantContext) -> date:
    return datetime.now(tz(ctx)).date()


def day_start(ctx: TenantContext, day: date) -> datetime:
    return datetime.combine(day, time(0), tzinfo=tz(ctx))


def require_branch(ctx: TenantContext, permission: str, branch_id: uuid.UUID) -> None:
    if not ctx.has_in_branch(permission, branch_id):
        raise deny(ctx, permission, "roster")


def active_member(db: Session, membership_id: uuid.UUID) -> Membership:
    member = db.get(Membership, membership_id)
    if member is None or member.status != "active":
        raise ValidationFailed("Choose an active staff member.")
    return member


def names(db: Session, membership_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not membership_ids:
        return {}
    return dict(
        db.execute(
            select(Membership.id, User.full_name)
            .join(User, User.id == Membership.user_id)
            .where(Membership.id.in_(membership_ids))
        ).all()
    )


def can_manage_member(db: Session, ctx: TenantContext, membership_id: uuid.UUID) -> bool:
    if ctx.has_org_wide("roster.manage"):
        return True
    scope = ctx.branch_scope("roster.manage") or set()
    branches = set(
        db.scalars(
            select(MembershipRole.branch_id).where(MembershipRole.membership_id == membership_id)
        )
    )
    # Staff with an organisation-wide role are managed by organisation-wide managers.
    return bool(scope & {b for b in branches if b is not None})


# --- Shifts ------------------------------------------------------------------------------


def _leave_overlapping(
    db: Session, membership_id: uuid.UUID, first: date, last: date
) -> LeaveRequest | None:
    return db.scalar(
        select(LeaveRequest).where(
            LeaveRequest.membership_id == membership_id,
            LeaveRequest.status == "approved",
            LeaveRequest.starts_on <= last,
            LeaveRequest.ends_on >= first,
        )
    )


def _check_shift(db: Session, ctx: TenantContext, data: ShiftWrite) -> None:
    require_branch(ctx, "roster.manage", data.branch_id)
    active_member(db, data.membership_id)
    first = data.starts_at.astimezone(tz(ctx)).date()
    last = (data.ends_at - timedelta(microseconds=1)).astimezone(tz(ctx)).date()
    if _leave_overlapping(db, data.membership_id, first, last):
        raise Conflict("This person is on approved leave then.", code="on_leave")


def _flush_shift(db: Session, shift: Shift) -> None:
    # Added inside the savepoint so a rejected row is discarded with it.
    try:
        with db.begin_nested():
            db.add(shift)
            db.flush()
    except IntegrityError as exc:
        if isinstance(exc.orig, ExclusionViolation):
            raise Conflict(
                "This person already has a shift that overlaps.", code="shift_overlap"
            ) from exc
        raise


def create_shift(db: Session, ctx: TenantContext, data: ShiftWrite) -> Shift:
    _check_shift(db, ctx, data)
    shift = Shift(
        organisation_id=ctx.organisation_id,
        status="scheduled",
        created_by=ctx.user_id,
        **data.model_dump(),
    )
    _flush_shift(db, shift)
    ctx.audit(
        db,
        "shift.created",
        "shift",
        shift.id,
        branch_id=shift.branch_id,
        details={
            "membership_id": str(shift.membership_id),
            "starts_at": shift.starts_at.isoformat(),
        },
    )
    return shift


def get_shift(db: Session, ctx: TenantContext, shift_id: uuid.UUID) -> Shift:
    shift = db.get(Shift, shift_id, with_for_update=True)
    if shift is None:
        raise NotFound("Shift not found.")
    require_branch(ctx, "roster.manage", shift.branch_id)
    if shift.status != "scheduled":
        raise Conflict("This shift was cancelled.")
    return shift


def update_shift(db: Session, ctx: TenantContext, shift: Shift, data: ShiftWrite) -> None:
    _check_shift(db, ctx, data)
    for key, value in data.model_dump().items():
        setattr(shift, key, value)
    _flush_shift(db, shift)
    ctx.audit(db, "shift.updated", "shift", shift.id, branch_id=shift.branch_id)


def cancel_shift(db: Session, ctx: TenantContext, shift: Shift) -> None:
    shift.status = "cancelled"
    ctx.audit(db, "shift.cancelled", "shift", shift.id, branch_id=shift.branch_id)


def copy_week(
    db: Session, ctx: TenantContext, branch_id: uuid.UUID, source: date, target: date
) -> tuple[int, int]:
    """Repeat a week's shifts in another week, skipping any that would clash."""
    require_branch(ctx, "roster.manage", branch_id)
    if source.weekday() != 0 or target.weekday() != 0:
        raise ValidationFailed("Weeks start on a Monday.")
    if source == target:
        raise ValidationFailed("Choose a different week.")
    shifts = db.scalars(
        select(Shift).where(
            Shift.branch_id == branch_id,
            Shift.status == "scheduled",
            Shift.starts_at >= day_start(ctx, source),
            Shift.starts_at < day_start(ctx, source + timedelta(days=7)),
        )
    ).all()
    created = skipped = 0
    for s in shifts:
        # Shift by calendar days in local time, so a 08:00 shift stays at 08:00.
        local_start = s.starts_at.astimezone(tz(ctx))
        new_start = datetime.combine(
            local_start.date() + (target - source), local_start.time(), tzinfo=tz(ctx)
        )
        data = ShiftWrite(
            branch_id=s.branch_id,
            membership_id=s.membership_id,
            starts_at=new_start,
            ends_at=new_start + (s.ends_at - s.starts_at),
            duty=s.duty,
            notes=s.notes,
        )
        try:
            create_shift(db, ctx, data)
            created += 1
        except (Conflict, ValidationFailed):
            skipped += 1
    return created, skipped


def shift_reads(db: Session, rows: list[Shift]) -> list[ShiftRead]:
    who = names(db, {s.membership_id for s in rows})
    return [
        ShiftRead.model_validate(
            {
                **{k: getattr(s, k) for k in ShiftRead.model_fields if k != "staff_name"},
                "staff_name": who.get(s.membership_id, ""),
            }
        )
        for s in rows
    ]


# --- Leave -------------------------------------------------------------------------------


def _flush_leave(db: Session, leave: LeaveRequest) -> None:
    try:
        with db.begin_nested():
            db.add(leave)
            db.flush()
    except IntegrityError as exc:
        if isinstance(exc.orig, ExclusionViolation):
            raise Conflict(
                "There is already leave requested or approved for these dates.",
                code="leave_overlap",
            ) from exc
        raise


def request_leave(
    db: Session, ctx: TenantContext, membership_id: uuid.UUID, data: LeaveCreate
) -> LeaveRequest:
    leave = LeaveRequest(
        organisation_id=ctx.organisation_id,
        membership_id=membership_id,
        starts_on=data.starts_on,
        ends_on=data.ends_on,
        leave_type=data.leave_type,
        reason=data.reason or None,
        status="requested",
        requested_by=ctx.user_id,
    )
    _flush_leave(db, leave)
    ctx.audit(
        db,
        "leave.requested",
        "leave",
        leave.id,
        details={
            "membership_id": str(membership_id),
            "starts_on": str(data.starts_on),
            "ends_on": str(data.ends_on),
        },
    )
    return leave


def get_leave(db: Session, leave_id: uuid.UUID) -> LeaveRequest:
    leave = db.get(LeaveRequest, leave_id, with_for_update=True)
    if leave is None:
        raise NotFound("Leave request not found.")
    return leave


def _provider_for(db: Session, membership_id: uuid.UUID) -> Provider | None:
    return db.scalar(
        select(Provider)
        .join(StaffProfile, StaffProfile.id == Provider.staff_profile_id)
        .where(StaffProfile.membership_id == membership_id)
    )


def _overlaps(db: Session, ctx: TenantContext, leave: LeaveRequest) -> tuple[int, int]:
    start, end = day_start(ctx, leave.starts_on), day_start(ctx, leave.ends_on + timedelta(days=1))
    shifts = db.scalar(
        select(func.count())
        .select_from(Shift)
        .where(
            Shift.membership_id == leave.membership_id,
            Shift.status == "scheduled",
            Shift.starts_at < end,
            Shift.ends_at > start,
        )
    )
    appointments = 0
    provider = _provider_for(db, leave.membership_id)
    if provider is not None:
        appointments = (
            db.scalar(
                select(func.count())
                .select_from(Appointment)
                .where(
                    Appointment.provider_id == provider.id,
                    Appointment.status.not_in(FINISHED_APPOINTMENTS),
                    Appointment.start_at < end,
                    Appointment.end_at > start,
                )
            )
            or 0
        )
    return appointments, shifts or 0


def decide(
    db: Session, ctx: TenantContext, leave: LeaveRequest, decision: str, note: str | None
) -> tuple[int, int]:
    if not can_manage_member(db, ctx, leave.membership_id):
        raise deny(ctx, "roster.manage", "leave")
    if leave.status != "requested":
        raise Conflict("This leave request has already been decided.")
    if decision == "approved" and leave.membership_id == ctx.membership.id:
        raise Forbidden("Someone else must approve your own leave.", code="own_leave")
    leave.status = decision
    leave.decided_by, leave.decided_at = ctx.user_id, datetime.now(UTC)
    leave.decision_note = note or None
    if decision == "approved":
        _block_bookings(db, ctx, leave)
    db.flush()
    ctx.audit(
        db,
        f"leave.{decision}",
        "leave",
        leave.id,
        details={"membership_id": str(leave.membership_id)},
    )
    return _overlaps(db, ctx, leave)


def _block_bookings(db: Session, ctx: TenantContext, leave: LeaveRequest) -> None:
    """Approved leave for a practitioner blocks their bookable time."""
    provider = _provider_for(db, leave.membership_id)
    if provider is None:
        return
    block = ProviderUnavailability(
        organisation_id=ctx.organisation_id,
        provider_id=provider.id,
        start_at=day_start(ctx, leave.starts_on),
        end_at=day_start(ctx, leave.ends_on + timedelta(days=1)),
        reason="Leave",
        created_by=ctx.user_id,
    )
    db.add(block)
    db.flush()
    leave.unavailability_id = block.id


def cancel_leave(db: Session, ctx: TenantContext, leave: LeaveRequest) -> None:
    own = leave.membership_id == ctx.membership.id
    if not own and not can_manage_member(db, ctx, leave.membership_id):
        raise deny(ctx, "roster.manage", "leave")
    if leave.status not in ("requested", "approved"):
        raise Conflict("This leave is not active.")
    if own and leave.status == "approved" and leave.starts_on <= local_today(ctx):
        raise Conflict("Leave that has started can only be changed by a manager.")
    if leave.unavailability_id is not None:
        block = db.get(ProviderUnavailability, leave.unavailability_id)
        leave.unavailability_id = None
        if block is not None:
            db.delete(block)
    leave.status = "cancelled"
    ctx.audit(
        db,
        "leave.cancelled",
        "leave",
        leave.id,
        details={"membership_id": str(leave.membership_id)},
    )


def leave_reads(
    db: Session, ctx: TenantContext, rows: list[LeaveRequest], *, detail: bool
) -> list[LeaveRead]:
    who = names(db, {r.membership_id for r in rows})
    deciders = dict(
        db.execute(
            select(User.id, User.full_name).where(
                User.id.in_({r.decided_by for r in rows if r.decided_by})
            )
        ).all()
    )
    out = []
    for r in rows:
        private = detail or r.membership_id == ctx.membership.id
        out.append(
            LeaveRead(
                id=r.id,
                membership_id=r.membership_id,
                staff_name=who.get(r.membership_id, ""),
                starts_on=r.starts_on,
                ends_on=r.ends_on,
                status=r.status,  # type: ignore[arg-type]
                leave_type=r.leave_type if private else None,  # type: ignore[arg-type]
                reason=r.reason if private else None,
                decided_by_name=deciders.get(r.decided_by) if r.decided_by else None,
                decided_at=r.decided_at,
                decision_note=r.decision_note if private else None,
                blocks_bookings=r.unavailability_id is not None,
            )
        )
    return out
