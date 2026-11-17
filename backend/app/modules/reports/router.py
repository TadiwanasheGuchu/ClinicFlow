import uuid
from datetime import date
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import ValidationFailed
from app.core.tenancy import TenantContext, deny, require
from app.modules.reports import service
from app.modules.reports.schemas import FinancialReport, OperationalReport

router = APIRouter(prefix="/reports", tags=["reports"])
DB = Annotated[Session, Depends(get_db)]
MAX_DAYS = 366


def _range(start: date, end: date) -> None:
    if end < start:
        raise ValidationFailed("The end date must be on or after the start date.")
    if (end - start).days >= MAX_DAYS:
        raise ValidationFailed("Reports cover at most one year.")


def _branch(
    ctx: TenantContext, permission: str, branch_id: uuid.UUID | None
) -> set[uuid.UUID] | None:
    if branch_id is not None and not ctx.has_in_branch(permission, branch_id):
        raise deny(ctx, permission, "report")
    return ctx.branch_scope(permission)


@router.get("/operational", response_model=OperationalReport)
def operational(
    ctx: Annotated[TenantContext, Depends(require("reports.operational"))],
    db: DB,
    start: date,
    end: date,
    branch_id: uuid.UUID | None = None,
) -> object:
    _range(start, end)
    scope = _branch(ctx, "reports.operational", branch_id)
    return service.operational(
        db,
        start=start,
        end=end,
        tz=ZoneInfo(ctx.organisation.timezone),
        branch_id=branch_id,
        scope=scope,
    )


@router.get("/financial", response_model=FinancialReport)
def financial(
    ctx: Annotated[TenantContext, Depends(require("reports.financial"))],
    db: DB,
    start: date,
    end: date,
    branch_id: uuid.UUID | None = None,
) -> object:
    _range(start, end)
    scope = _branch(ctx, "reports.financial", branch_id)
    return service.financial(
        db,
        start=start,
        end=end,
        tz=ZoneInfo(ctx.organisation.timezone),
        branch_id=branch_id,
        scope=scope,
    )
