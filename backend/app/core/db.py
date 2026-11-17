"""Database engine, session and tenant-scoping hooks.

Tenant scope is carried on ``Session.info`` and re-applied as transaction-local
PostgreSQL settings at the start of every transaction. Row-Level Security
policies read these settings, so a query issued without a tenant scope sees no
tenant rows at all.
"""

import uuid
from collections.abc import Iterator
from datetime import datetime
from functools import lru_cache

from sqlalchemy import DateTime, Engine, create_engine, event, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import get_settings

SCOPE_ORGANISATION = "organisation_id"
SCOPE_USER = "user_id"
SCOPE_PLATFORM = "platform_scope"
SCOPE_WORKER = "worker_scope"


class Base(DeclarativeBase):
    pass


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def _apply_scope(session: Session, connection) -> None:  # type: ignore[no-untyped-def]
    for key in (SCOPE_ORGANISATION, SCOPE_USER, SCOPE_PLATFORM, SCOPE_WORKER):
        value = session.info.get(key)
        connection.execute(
            text("SELECT set_config(:name, :value, true)"),
            {"name": f"app.{key}", "value": "" if value is None else str(value)},
        )


@event.listens_for(Session, "after_begin")
def _on_transaction_begin(session: Session, transaction, connection) -> None:  # type: ignore[no-untyped-def]
    _apply_scope(session, connection)


def set_scope(
    session: Session,
    *,
    organisation_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    platform: bool = False,
    worker: bool = False,
) -> None:
    """Set the tenant scope for this session and apply it to the open transaction."""
    session.info[SCOPE_ORGANISATION] = organisation_id
    session.info[SCOPE_USER] = user_id
    session.info[SCOPE_PLATFORM] = "on" if platform else None
    session.info[SCOPE_WORKER] = "on" if worker else None
    if session.in_transaction():
        _apply_scope(session, session.connection())


def get_db() -> Iterator[Session]:
    """Request-scoped session. Handlers that write must call ``db.commit()`` explicitly
    before returning, so a failed commit can never follow a success response."""
    session = get_sessionmaker()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
