from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import CurrentUserDep
from app.core.tenancy import TenantContext, require
from app.modules.organisations.schemas import (
    OrganisationCreate,
    OrganisationRead,
    OrganisationSettings,
    OrganisationUpdate,
)
from app.modules.organisations.service import register_organisation
from app.modules.portal import slugs

router = APIRouter(tags=["organisations"])
DB = Annotated[Session, Depends(get_db)]


@router.post("/organisations", response_model=OrganisationRead, status_code=status.HTTP_201_CREATED)
def create_organisation(data: OrganisationCreate, current: CurrentUserDep, db: DB) -> object:
    """Register a new practice. The caller becomes its Owner."""
    organisation = register_organisation(db, current, data)
    db.commit()
    return _read(db, organisation)


@router.get("/organisation", response_model=OrganisationRead)
def get_organisation(
    ctx: Annotated[TenantContext, Depends(require("organisation.read"))], db: DB
) -> object:
    return _read(db, ctx.organisation)


@router.patch("/organisation", response_model=OrganisationRead)
def update_organisation(
    data: OrganisationUpdate,
    ctx: Annotated[TenantContext, Depends(require("organisation.manage", org_wide=True))],
    db: DB,
) -> object:
    organisation = ctx.organisation
    changes = data.model_dump(exclude_unset=True, exclude={"settings", "slug"})
    if data.slug is not None:
        before_slug = slugs.slug_of(db, organisation.id)
        slugs.change(db, organisation.id, data.slug)
        if before_slug != data.slug:
            ctx.audit(
                db,
                "organisation.portal_address_changed",
                "organisation",
                organisation.id,
                details={"from": before_slug, "to": data.slug},
            )
    before = {key: getattr(organisation, key) for key in changes}
    for key, value in changes.items():
        setattr(organisation, key, value)

    if data.settings is not None:
        current_settings = OrganisationSettings.model_validate(organisation.settings or {})
        updated = current_settings.model_copy(update=data.settings.model_dump(exclude_unset=True))
        before["settings"] = current_settings.model_dump()
        changes["settings"] = updated.model_dump()
        organisation.settings = changes["settings"]

    ctx.audit(
        db,
        "organisation.updated",
        "organisation",
        organisation.id,
        details={"before": before, "after": changes},
    )
    db.commit()
    return _read(db, organisation)


def _read(db: Session, organisation: object) -> OrganisationRead:
    read = OrganisationRead.model_validate(organisation)
    read.slug = slugs.slug_of(db, read.id)
    return read
