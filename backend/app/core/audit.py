"""Audit logging.

``record`` writes in the caller's transaction, so the audit event commits or
rolls back together with the change it describes. ``record_independent``
commits in its own transaction and is used for events that must survive a
failed request, such as denied access attempts.
"""

import ipaddress
import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.db import get_sessionmaker, set_scope
from app.core.request_context import request_id_var, source_ip_var
from app.modules.audit.models import AuditLog

logger = logging.getLogger(__name__)


def _source_ip() -> str | None:
    ip = source_ip_var.get()
    if not ip:
        return None
    try:
        return str(ipaddress.ip_address(ip))
    except ValueError:
        return None


def _build(
    *,
    action: str,
    resource_type: str,
    organisation_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
    resource_id: uuid.UUID | None,
    branch_id: uuid.UUID | None,
    details: dict[str, Any] | None,
) -> AuditLog:
    return AuditLog(
        organisation_id=organisation_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        branch_id=branch_id,
        request_id=request_id_var.get(),
        source_ip=_source_ip(),
        details=details or {},
    )


def record(
    db: Session,
    *,
    action: str,
    resource_type: str,
    organisation_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
    resource_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        _build(
            action=action,
            resource_type=resource_type,
            organisation_id=organisation_id,
            actor_user_id=actor_user_id,
            resource_id=resource_id,
            branch_id=branch_id,
            details=details,
        )
    )


def record_independent(
    *,
    action: str,
    resource_type: str,
    organisation_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
    resource_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    session = get_sessionmaker()()
    try:
        set_scope(session, organisation_id=organisation_id, user_id=actor_user_id)
        session.add(
            _build(
                action=action,
                resource_type=resource_type,
                organisation_id=organisation_id,
                actor_user_id=actor_user_id,
                resource_id=resource_id,
                branch_id=None,
                details=details,
            )
        )
        session.commit()
    except Exception:
        # Never let audit failure mask the original response, but make it loud.
        logger.exception("Failed to write independent audit event %s", action)
        session.rollback()
    finally:
        session.close()
