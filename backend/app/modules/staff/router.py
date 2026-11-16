import uuid
from datetime import UTC, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import Forbidden, NotFound, ValidationFailed
from app.core.tenancy import TenantContext, require
from app.modules.members.service import get_membership
from app.modules.staff import service
from app.modules.staff.models import StaffProfile
from app.modules.staff.schemas import StaffProfileRead, StaffProfileUpdate, Verification

router = APIRouter(prefix="/members/{membership_id}/profile", tags=["staff"])
DB = Annotated[Session, Depends(get_db)]

# Changing any of these invalidates an earlier verification.
_REGISTRATION_FIELDS = (
    "profession",
    "registration_body",
    "professional_number",
    "licence_expiry_date",
)


@router.get("", response_model=StaffProfileRead)
def read_profile(
    membership_id: uuid.UUID,
    ctx: Annotated[TenantContext, Depends(require("members.read"))],
    db: DB,
) -> object:
    get_membership(db, membership_id)
    profile = service.get_profile(db, membership_id)
    if profile is None:
        raise NotFound("No professional profile recorded.")
    return service.to_read(profile, ctx.organisation.timezone)


@router.put("", response_model=StaffProfileRead)
def upsert_profile(
    membership_id: uuid.UUID,
    data: StaffProfileUpdate,
    ctx: Annotated[TenantContext, Depends(require("members.manage", org_wide=True))],
    db: DB,
) -> object:
    get_membership(db, membership_id)
    profile = service.get_profile(db, membership_id)
    created = profile is None
    if profile is None:
        profile = StaffProfile(
            organisation_id=ctx.organisation_id,
            membership_id=membership_id,
            registration_status="unverified",
        )
        db.add(profile)

    values = data.model_dump()
    changed = {
        k: {"before": str(getattr(profile, k)) if not created else None, "after": str(v)}
        for k, v in values.items()
        if created or getattr(profile, k) != v
    }
    reset = not created and any(k in changed for k in _REGISTRATION_FIELDS)
    for key, value in values.items():
        setattr(profile, key, value)
    if reset and profile.registration_status != "unverified":
        profile.registration_status = "unverified"
        profile.verified_by = None
        profile.verified_at = None
        profile.verification_note = None
    db.flush()
    ctx.audit(
        db,
        "staff_profile.created" if created else "staff_profile.updated",
        "staff_profile",
        profile.id,
        details={
            "membership_id": str(membership_id),
            "changes": changed,
            "verification_reset": reset,
        },
    )
    db.commit()
    return service.to_read(profile, ctx.organisation.timezone)


@router.post("/verify", response_model=StaffProfileRead)
def verify_profile(
    membership_id: uuid.UUID,
    data: Verification,
    ctx: Annotated[TenantContext, Depends(require("credentials.verify", org_wide=True))],
    db: DB,
) -> object:
    if membership_id == ctx.membership.id:
        raise Forbidden("You cannot verify your own registration.", code="self_verification")
    get_membership(db, membership_id)
    profile = service.get_profile(db, membership_id)
    if profile is None:
        raise NotFound("No professional profile recorded.")
    if data.decision == "verified":
        if not profile.professional_number or not profile.registration_body:
            raise ValidationFailed("Record the registration body and number before verifying.")
        if profile.licence_expiry_date is None:
            raise ValidationFailed("Record the licence expiry date before verifying.")
        if profile.licence_expiry_date < datetime.now(ZoneInfo(ctx.organisation.timezone)).date():
            raise ValidationFailed("The licence has expired; it cannot be verified.")
    profile.registration_status = data.decision
    profile.verified_by = ctx.user_id
    profile.verified_at = datetime.now(UTC)
    profile.verification_note = data.note
    ctx.audit(
        db,
        f"staff_profile.{data.decision}",
        "staff_profile",
        profile.id,
        details={"membership_id": str(membership_id), "note": data.note},
    )
    db.commit()
    return service.to_read(profile, ctx.organisation.timezone)
