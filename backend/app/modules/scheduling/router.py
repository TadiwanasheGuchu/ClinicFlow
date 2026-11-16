import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import Conflict, NotFound, ValidationFailed
from app.core.tenancy import TenantContext, require
from app.modules.branches.models import Branch
from app.modules.members.models import Membership
from app.modules.organisations.schemas import OrganisationSettings
from app.modules.scheduling import service
from app.modules.scheduling.models import (
    AppointmentType,
    Provider,
    ProviderAvailability,
    ProviderUnavailability,
)
from app.modules.scheduling.schemas import (
    AppointmentTypeCreate,
    AppointmentTypeRead,
    AppointmentTypeUpdate,
    AvailabilityRead,
    AvailabilityReplace,
    ProviderCreate,
    ProviderRead,
    ProviderUpdate,
    Slot,
    UnavailabilityCreate,
    UnavailabilityRead,
)
from app.modules.staff.models import StaffProfile
from app.modules.staff.schemas import CLINICAL_PROFESSIONS
from app.modules.staff.service import get_profile, is_cleared
from app.modules.users.models import User

router = APIRouter(tags=["scheduling"])
DB = Annotated[Session, Depends(get_db)]
CanRead = Annotated[TenantContext, Depends(require("appointments.read"))]
CanManage = Annotated[TenantContext, Depends(require("scheduling.manage", org_wide=True))]


# --- Appointment types ---------------------------------------------------------


@router.get("/appointment-types", response_model=list[AppointmentTypeRead])
def list_types(ctx: CanRead, db: DB, include_inactive: bool = False) -> object:
    query = select(AppointmentType).order_by(AppointmentType.name)
    if not include_inactive:
        query = query.where(AppointmentType.is_active.is_(True))
    return db.scalars(query).all()


@router.post(
    "/appointment-types", response_model=AppointmentTypeRead, status_code=status.HTTP_201_CREATED
)
def create_type(data: AppointmentTypeCreate, ctx: CanManage, db: DB) -> object:
    item = AppointmentType(organisation_id=ctx.organisation_id, is_active=True, **data.model_dump())
    db.add(item)
    try:
        db.flush()
    except IntegrityError as exc:
        raise Conflict("An appointment type with this name already exists.") from exc
    ctx.audit(
        db,
        "appointment_type.created",
        "appointment_type",
        item.id,
        details=data.model_dump(mode="json"),
    )
    db.commit()
    return item


@router.patch("/appointment-types/{type_id}", response_model=AppointmentTypeRead)
def update_type(type_id: uuid.UUID, data: AppointmentTypeUpdate, ctx: CanManage, db: DB) -> object:
    item = service.get_appointment_type(db, type_id)
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(item, key, value)
    try:
        db.flush()
    except IntegrityError as exc:
        raise Conflict("An appointment type with this name already exists.") from exc
    ctx.audit(
        db,
        "appointment_type.updated",
        "appointment_type",
        item.id,
        details=data.model_dump(mode="json", exclude_unset=True),
    )
    db.commit()
    return item


# --- Providers -----------------------------------------------------------------


def _provider_reads(
    db: Session, ctx: TenantContext, providers: list[Provider]
) -> list[ProviderRead]:
    if not providers:
        return []
    profiles = {
        p.id: p
        for p in db.scalars(
            select(StaffProfile).where(StaffProfile.id.in_([p.staff_profile_id for p in providers]))
        )
    }
    memberships = {
        m.id: m
        for m in db.scalars(
            select(Membership).where(
                Membership.id.in_([p.membership_id for p in profiles.values()])
            )
        )
    }
    branch_rows = db.execute(
        select(ProviderAvailability.provider_id, ProviderAvailability.branch_id)
        .where(ProviderAvailability.provider_id.in_([p.id for p in providers]))
        .distinct()
    ).all()
    branches: dict[uuid.UUID, list[uuid.UUID]] = {}
    for provider_id, branch_id in branch_rows:
        branches.setdefault(provider_id, []).append(branch_id)
    result = []
    for p in providers:
        profile = profiles[p.staff_profile_id]
        membership = memberships.get(profile.membership_id)
        result.append(
            ProviderRead(
                id=p.id,
                membership_id=profile.membership_id,
                display_name=p.display_name,
                profession=profile.profession,
                specialty=profile.specialty,
                booking_enabled=p.booking_enabled,
                online_booking_enabled=p.online_booking_enabled,
                credentials_current=bool(
                    membership
                    and membership.status == "active"
                    and is_cleared(profile, ctx.organisation.timezone)
                ),
                branch_ids=sorted(branches.get(p.id, []), key=str),
            )
        )
    return result


@router.get("/providers", response_model=list[ProviderRead])
def list_providers(
    ctx: CanRead,
    db: DB,
    branch_id: uuid.UUID | None = None,
    bookable_only: bool = False,
) -> object:
    query = select(Provider).order_by(Provider.display_name)
    if branch_id:
        query = query.where(
            Provider.id.in_(
                select(ProviderAvailability.provider_id).where(
                    ProviderAvailability.branch_id == branch_id
                )
            )
        )
    reads = _provider_reads(db, ctx, list(db.scalars(query)))
    if bookable_only:
        reads = [r for r in reads if r.booking_enabled and r.credentials_current]
    return reads


@router.get("/providers/{provider_id}", response_model=ProviderRead)
def read_provider(provider_id: uuid.UUID, ctx: CanRead, db: DB) -> object:
    return _provider_reads(db, ctx, [service.get_provider(db, provider_id)])[0]


@router.post("/providers", response_model=ProviderRead, status_code=status.HTTP_201_CREATED)
def create_provider(data: ProviderCreate, ctx: CanManage, db: DB) -> object:
    membership = db.get(Membership, data.membership_id)
    if membership is None:
        raise NotFound("Member not found.")
    profile = get_profile(db, membership.id)
    if profile is None or profile.profession not in CLINICAL_PROFESSIONS:
        raise ValidationFailed(
            "Record this person's clinical profession before adding them as a practitioner."
        )
    if not is_cleared(profile, ctx.organisation.timezone):
        raise ValidationFailed(
            "Their professional registration must be verified and current before they can "
            "take bookings.",
            code="credentials_not_verified",
        )
    user = db.get_one(User, membership.user_id)
    provider = Provider(
        organisation_id=ctx.organisation_id,
        staff_profile_id=profile.id,
        display_name=data.display_name or user.full_name,
        booking_enabled=True,
        online_booking_enabled=data.online_booking_enabled,
    )
    db.add(provider)
    try:
        db.flush()
    except IntegrityError as exc:
        raise Conflict("This person is already set up as a practitioner.") from exc
    ctx.audit(
        db,
        "provider.created",
        "provider",
        provider.id,
        details={"membership_id": str(membership.id)},
    )
    db.commit()
    return _provider_reads(db, ctx, [provider])[0]


@router.patch("/providers/{provider_id}", response_model=ProviderRead)
def update_provider(provider_id: uuid.UUID, data: ProviderUpdate, ctx: CanManage, db: DB) -> object:
    provider = service.get_provider(db, provider_id)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("booking_enabled") and not is_cleared(
        service.provider_profile(db, provider), ctx.organisation.timezone
    ):
        raise ValidationFailed(
            "Their professional registration must be verified and current before they can "
            "take bookings.",
            code="credentials_not_verified",
        )
    for key, value in changes.items():
        setattr(provider, key, value)
    ctx.audit(db, "provider.updated", "provider", provider.id, details=changes)
    db.commit()
    return _provider_reads(db, ctx, [provider])[0]


# --- Availability ----------------------------------------------------------------


@router.get("/providers/{provider_id}/availability", response_model=list[AvailabilityRead])
def read_availability(provider_id: uuid.UUID, ctx: CanRead, db: DB) -> object:
    service.get_provider(db, provider_id)
    return db.scalars(
        select(ProviderAvailability)
        .where(ProviderAvailability.provider_id == provider_id)
        .order_by(ProviderAvailability.weekday, ProviderAvailability.start_time)
    ).all()


@router.put("/providers/{provider_id}/availability", response_model=list[AvailabilityRead])
def replace_availability(
    provider_id: uuid.UUID, data: AvailabilityReplace, ctx: CanManage, db: DB
) -> object:
    """Replace the provider's weekly working hours. Existing bookings are not changed."""
    service.get_provider(db, provider_id)
    branch_ids = {w.branch_id for w in data.windows}
    if branch_ids:
        found = set(
            db.scalars(
                select(Branch.id).where(Branch.id.in_(branch_ids), Branch.is_active.is_(True))
            )
        )
        if found != branch_ids:
            raise ValidationFailed("One or more branches do not exist or are inactive.")
    db.execute(delete(ProviderAvailability).where(ProviderAvailability.provider_id == provider_id))
    rows = [
        ProviderAvailability(
            organisation_id=ctx.organisation_id, provider_id=provider_id, **w.model_dump()
        )
        for w in data.windows
    ]
    db.add_all(rows)
    db.flush()
    ctx.audit(
        db,
        "provider.availability_replaced",
        "provider",
        provider_id,
        details={"windows": [w.model_dump(mode="json") for w in data.windows]},
    )
    db.commit()
    return sorted(rows, key=lambda r: (r.weekday, r.start_time))


@router.get("/providers/{provider_id}/unavailability", response_model=list[UnavailabilityRead])
def list_unavailability(
    provider_id: uuid.UUID, ctx: CanRead, db: DB, upcoming_only: bool = True
) -> object:
    service.get_provider(db, provider_id)
    query = select(ProviderUnavailability).where(ProviderUnavailability.provider_id == provider_id)
    if upcoming_only:
        query = query.where(ProviderUnavailability.end_at > datetime.now(UTC))
    return db.scalars(query.order_by(ProviderUnavailability.start_at)).all()


@router.post(
    "/providers/{provider_id}/unavailability",
    response_model=UnavailabilityRead,
    status_code=status.HTTP_201_CREATED,
)
def add_unavailability(
    provider_id: uuid.UUID, data: UnavailabilityCreate, ctx: CanManage, db: DB
) -> object:
    """Block time (leave, training). Existing bookings in the period are reported, not cancelled."""
    service.get_provider(db, provider_id)
    item = ProviderUnavailability(
        organisation_id=ctx.organisation_id,
        provider_id=provider_id,
        created_by=ctx.user_id,
        **data.model_dump(),
    )
    db.add(item)
    db.flush()
    ctx.audit(
        db,
        "provider.unavailability_added",
        "provider",
        provider_id,
        details={
            "start_at": data.start_at.isoformat(),
            "end_at": data.end_at.isoformat(),
            "reason": data.reason,
        },
    )
    db.commit()
    return item


@router.delete(
    "/providers/{provider_id}/unavailability/{item_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_unavailability(
    provider_id: uuid.UUID, item_id: uuid.UUID, ctx: CanManage, db: DB
) -> Response:
    item = db.get(ProviderUnavailability, item_id)
    if item is None or item.provider_id != provider_id:
        raise NotFound("Blocked period not found.")
    ctx.audit(
        db,
        "provider.unavailability_removed",
        "provider",
        provider_id,
        details={"start_at": item.start_at.isoformat(), "end_at": item.end_at.isoformat()},
    )
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Slots -----------------------------------------------------------------------


@router.get("/providers/{provider_id}/slots", response_model=list[Slot])
def list_slots(
    provider_id: uuid.UUID,
    ctx: CanRead,
    db: DB,
    branch_id: uuid.UUID,
    appointment_type_id: uuid.UUID,
    day: Annotated[date, Query(alias="date")],
) -> object:
    provider = service.get_provider(db, provider_id)
    appointment_type = service.get_appointment_type(db, appointment_type_id)
    if not provider_bookable_or_false(db, provider, ctx) or not appointment_type.is_active:
        return []
    settings = OrganisationSettings.model_validate(ctx.organisation.settings or {})
    windows = service.free_slots(
        db,
        provider=provider,
        branch_id=branch_id,
        day=day,
        appointment_type=appointment_type,
        timezone=ctx.organisation.timezone,
        step_minutes=settings.default_appointment_minutes,
    )
    return [Slot(start_at=w.start, end_at=w.end) for w in windows]


def provider_bookable_or_false(db: Session, provider: Provider, ctx: TenantContext) -> bool:
    return service.provider_bookable(db, provider, ctx.organisation.timezone)
