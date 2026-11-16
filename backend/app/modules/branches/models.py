import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey


class Branch(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "branches"
    __table_args__ = (
        UniqueConstraint("organisation_id", "branch_code"),
        # Target for composite foreign keys that pin references to the same tenant.
        UniqueConstraint("organisation_id", "id", name="uq_branches_org_id"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    branch_code: Mapped[str] = mapped_column(String(20))
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(320))
    operating_hours: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
