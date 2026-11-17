import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict
from app.modules.portal.models import OrganisationSlug

SLUG_PATTERN = r"^[a-z0-9](?:[a-z0-9-]{1,58}[a-z0-9])$"
RESERVED = {"new", "admin", "api", "app", "book", "portal", "signin", "clinicflow"}


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:50].strip("-")
    return slug if len(slug) >= 3 else f"practice-{slug}".strip("-")


def assign_unique(db: Session, organisation_id: uuid.UUID, name: str) -> str:
    base = slugify(name)
    slug, n = base, 2
    while slug in RESERVED or db.get(OrganisationSlug, slug) is not None:
        slug, n = f"{base}-{n}", n + 1
    db.add(OrganisationSlug(slug=slug, organisation_id=organisation_id))
    return slug


def slug_of(db: Session, organisation_id: uuid.UUID) -> str | None:
    return db.scalar(
        select(OrganisationSlug.slug).where(OrganisationSlug.organisation_id == organisation_id)
    )


def change(db: Session, organisation_id: uuid.UUID, new_slug: str) -> None:
    if new_slug in RESERVED:
        raise Conflict("That address is reserved. Choose another.")
    existing = db.get(OrganisationSlug, new_slug)
    if existing is not None and existing.organisation_id != organisation_id:
        raise Conflict("That address is already used by another practice.")
    current = db.scalar(
        select(OrganisationSlug).where(OrganisationSlug.organisation_id == organisation_id)
    )
    if current is None:
        db.add(OrganisationSlug(slug=new_slug, organisation_id=organisation_id))
    elif current.slug != new_slug:
        db.delete(current)
        db.flush()
        db.add(OrganisationSlug(slug=new_slug, organisation_id=organisation_id))


def resolve(db: Session, slug: str) -> uuid.UUID | None:
    row = db.get(OrganisationSlug, slug.lower())
    return row.organisation_id if row else None
