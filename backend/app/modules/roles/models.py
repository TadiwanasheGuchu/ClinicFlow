import uuid

from sqlalchemy import (
    Boolean,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey


class Permission(UUIDPrimaryKey, Base):
    """Global permission catalogue, synchronised from app.core.permissions."""

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text)
    privileged: Mapped[bool] = mapped_column(Boolean, default=False)


class Role(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("organisation_id", "name"),
        UniqueConstraint("organisation_id", "template_key"),
        UniqueConstraint("organisation_id", "id", name="uq_roles_org_id"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    # Set for roles created from a template (e.g. "owner"); null for custom roles.
    template_key: Mapped[str | None] = mapped_column(String(50))
    # System roles cannot be renamed, edited or deleted.
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organisation_id", "role_id"],
            ["roles.organisation_id", "roles.id"],
            ondelete="CASCADE",
            name="fk_role_permissions_role_same_org",
        ),
    )

    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("permissions.id"), primary_key=True)
    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
