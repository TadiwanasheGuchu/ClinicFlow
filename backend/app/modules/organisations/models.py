import uuid
from typing import Any

from sqlalchemy import CHAR, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey


class Organisation(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "organisations"

    name: Mapped[str] = mapped_column(String(200))
    legal_name: Mapped[str | None] = mapped_column(String(200))
    registration_number: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(CHAR(3), default="NAD")
    timezone: Mapped[str] = mapped_column(String(64), default="Africa/Windhoek")
    status: Mapped[str] = mapped_column(String(20), default="active")
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
