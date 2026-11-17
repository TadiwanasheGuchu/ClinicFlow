"""Request context for the patient portal.

Patients are not organisation members. A portal request names the practice by its public
slug; the database session is scoped to that organisation, and every query for patient
data is additionally filtered by the patient record linked to the signed-in account.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.db import get_db, set_scope
from app.core.exceptions import Forbidden, NotFound
from app.core.security import CurrentUser, CurrentUserDep
from app.modules.organisations.models import Organisation
from app.modules.organisations.schemas import OrganisationSettings
from app.modules.patients.models import Patient
from app.modules.portal import slugs
from app.modules.portal.models import PatientAccount

SlugParam = Annotated[str, Path(pattern=r"^[a-z0-9-]{3,60}$")]


def _organisation(db: Session, slug: str) -> tuple[Organisation, OrganisationSettings]:
    organisation_id = slugs.resolve(db, slug)
    if organisation_id is None:
        raise NotFound("Practice not found.")
    set_scope(db, organisation_id=organisation_id)
    organisation = db.get(Organisation, organisation_id)
    settings = OrganisationSettings.model_validate(
        (organisation.settings if organisation else {}) or {}
    )
    if organisation is None or organisation.status != "active" or not settings.portal_enabled:
        raise NotFound("This practice does not offer online booking.")
    return organisation, settings


@dataclass
class PublicPortal:
    organisation: Organisation
    settings: OrganisationSettings
    slug: str


def public_portal(slug: SlugParam, db: Annotated[Session, Depends(get_db)]) -> PublicPortal:
    organisation, settings = _organisation(db, slug)
    return PublicPortal(organisation=organisation, settings=settings, slug=slug)


@dataclass
class PortalContext:
    organisation: Organisation
    settings: OrganisationSettings
    current: CurrentUser
    account: PatientAccount | None
    patient: Patient | None
    slug: str

    @property
    def organisation_id(self) -> uuid.UUID:
        return self.organisation.id

    @property
    def user_id(self) -> uuid.UUID:
        return self.current.id

    def has_in_branch(self, permission: str, branch_id: uuid.UUID) -> bool:
        return False  # Patients never hold staff permissions (e.g. scheduling overrides).

    def audit(
        self,
        db: Session,
        action: str,
        resource_type: str,
        resource_id: uuid.UUID | None = None,
        *,
        branch_id: uuid.UUID | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        audit.record(
            db,
            action=action,
            resource_type=resource_type,
            organisation_id=self.organisation_id,
            actor_user_id=self.user_id,
            resource_id=resource_id,
            branch_id=branch_id,
            details={"via": "patient_portal", **(details or {})},
        )


def portal_context(
    slug: SlugParam, current: CurrentUserDep, db: Annotated[Session, Depends(get_db)]
) -> PortalContext:
    organisation, settings = _organisation(db, slug)
    set_scope(db, organisation_id=organisation.id, user_id=current.id)
    account = db.scalar(
        select(PatientAccount).where(
            PatientAccount.user_id == current.id, PatientAccount.status == "active"
        )
    )
    patient = db.get(Patient, account.patient_id) if account else None
    if patient is not None and patient.status != "active":
        patient = None
    return PortalContext(organisation, settings, current, account, patient, slug)


PortalDep = Annotated[PortalContext, Depends(portal_context)]


def linked(ctx: PortalDep) -> PortalContext:
    if ctx.patient is None:
        raise Forbidden("Connect your account to your patient record first.", code="not_linked")
    return ctx


LinkedDep = Annotated[PortalContext, Depends(linked)]
