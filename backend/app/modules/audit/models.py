import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, func, text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UUIDPrimaryKey


class AuditLog(UUIDPrimaryKey, Base):
    """Append-only audit event. UPDATE/DELETE/TRUNCATE are blocked by database triggers."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_org_timestamp", "organisation_id", text('"timestamp" DESC')),
    )

    organisation_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column()
    action: Mapped[str] = mapped_column(String(100), index=True)
    resource_type: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[uuid.UUID | None] = mapped_column()
    branch_id: Mapped[uuid.UUID | None] = mapped_column()
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        # Client-side default so INSERTs need no RETURNING: a RETURNING row must
        # also satisfy the SELECT policy, which platform-level events do not.
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        index=True,
    )
    request_id: Mapped[str | None] = mapped_column(String(64))
    source_ip: Mapped[str | None] = mapped_column(INET)
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
