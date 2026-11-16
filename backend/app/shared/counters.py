"""Per-organisation human-readable numbering (patient numbers, appointment references).

``next_value`` increments atomically with a row lock, so concurrent requests can
never receive the same number.
"""

import uuid

from sqlalchemy import BigInteger, ForeignKey, String, text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.db import Base


class OrganisationCounter(Base):
    __tablename__ = "organisation_counters"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisations.id"), primary_key=True
    )
    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[int] = mapped_column(BigInteger, default=0)


def next_value(db: Session, organisation_id: uuid.UUID, name: str) -> int:
    return db.execute(
        text(
            "INSERT INTO organisation_counters (organisation_id, name, value) "
            "VALUES (:org, :name, 1) "
            "ON CONFLICT (organisation_id, name) "
            "DO UPDATE SET value = organisation_counters.value + 1 "
            "RETURNING value"
        ),
        {"org": organisation_id, "name": name},
    ).scalar_one()


def format_number(prefix: str, value: int, width: int = 6) -> str:
    return f"{prefix}-{value:0{width}d}"
