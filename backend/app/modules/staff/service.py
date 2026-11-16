import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.staff.models import StaffProfile
from app.modules.staff.schemas import StaffProfileRead


def get_profile(db: Session, membership_id: uuid.UUID) -> StaffProfile | None:
    return db.scalar(select(StaffProfile).where(StaffProfile.membership_id == membership_id))


def is_cleared(profile: StaffProfile | None, timezone: str) -> bool:
    """Verified registration with a licence that has not expired."""
    if profile is None or profile.registration_status != "verified":
        return False
    if profile.licence_expiry_date is None:
        return False
    return profile.licence_expiry_date >= datetime.now(ZoneInfo(timezone)).date()


def to_read(profile: StaffProfile, timezone: str) -> StaffProfileRead:
    return StaffProfileRead.model_validate(
        {
            **{
                f: getattr(profile, f)
                for f in StaffProfileRead.model_fields
                if f != "licence_current"
            },
            "licence_current": is_cleared(profile, timezone),
        }
    )
