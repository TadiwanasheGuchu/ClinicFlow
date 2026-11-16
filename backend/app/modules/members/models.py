import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey


class Membership(UUIDPrimaryKey, Timestamps, Base):
    """A user's membership of an organisation (one per user per organisation)."""

    __tablename__ = "organisation_memberships"
    __table_args__ = (
        UniqueConstraint("organisation_id", "user_id"),
        UniqueConstraint("organisation_id", "id", name="uq_memberships_org_id"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="invited")  # invited|active|suspended
    invited_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MembershipRole(UUIDPrimaryKey, Timestamps, Base):
    """A role granted to a member, either organisation-wide (branch_id null) or for one branch."""

    __tablename__ = "membership_roles"
    __table_args__ = (
        UniqueConstraint(
            "membership_id", "role_id", "branch_id", postgresql_nulls_not_distinct=True
        ),
        # Composite keys guarantee the membership, role and branch all belong to
        # the same organisation as this row.
        ForeignKeyConstraint(
            ["organisation_id", "membership_id"],
            ["organisation_memberships.organisation_id", "organisation_memberships.id"],
            ondelete="CASCADE",
            name="fk_membership_roles_membership_same_org",
        ),
        ForeignKeyConstraint(
            ["organisation_id", "role_id"],
            ["roles.organisation_id", "roles.id"],
            name="fk_membership_roles_role_same_org",
        ),
        ForeignKeyConstraint(
            ["organisation_id", "branch_id"],
            ["branches.organisation_id", "branches.id"],
            name="fk_membership_roles_branch_same_org",
        ),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"), index=True)
    membership_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organisation_memberships.id", ondelete="CASCADE"), index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), index=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"))
