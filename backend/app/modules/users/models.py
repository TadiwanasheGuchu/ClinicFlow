from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey


class User(UUIDPrimaryKey, Timestamps, Base):
    """A person who can sign in. Global identity; organisation access is via memberships."""

    __tablename__ = "users"
    __table_args__ = (Index("uq_users_email_lower", text("lower(email)"), unique=True),)

    # `sub` claim from the identity provider. Null until the invited user first signs in.
    identity_provider_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(320))  # stored lower-cased; unique index
    phone: Mapped[str | None] = mapped_column(String(32))
    full_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="active")
    # Platform administrators manage tenants and subscriptions. This grants NO
    # access to any organisation's patient or clinical data.
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
