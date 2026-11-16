import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import Conflict, NotFound
from app.core.tenancy import TenantContext, deny, require
from app.modules.branches.models import Branch
from app.modules.branches.schemas import BranchCreate, BranchRead, BranchUpdate
from app.shared.schemas import Page, PageParams

router = APIRouter(prefix="/branches", tags=["branches"])
DB = Annotated[Session, Depends(get_db)]


def get_branch(db: Session, branch_id: uuid.UUID) -> Branch:
    # RLS restricts this lookup to the current organisation; another tenant's
    # branch id is indistinguishable from a non-existent one.
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise NotFound("Branch not found.")
    return branch


@router.get("", response_model=Page[BranchRead])
def list_branches(
    ctx: Annotated[TenantContext, Depends(require("branches.read"))],
    db: DB,
    page: Annotated[PageParams, Depends()],
    include_inactive: Annotated[bool, Query()] = False,
) -> object:
    query = select(Branch)
    if not include_inactive:
        query = query.where(Branch.is_active.is_(True))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(Branch.name).limit(page.limit).offset(page.offset)).all()
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.post("", response_model=BranchRead, status_code=status.HTTP_201_CREATED)
def create_branch(
    data: BranchCreate,
    ctx: Annotated[TenantContext, Depends(require("branches.manage", org_wide=True))],
    db: DB,
) -> object:
    branch = Branch(organisation_id=ctx.organisation_id, **data.model_dump(mode="json"))
    db.add(branch)
    try:
        db.flush()
    except IntegrityError as exc:
        raise Conflict("A branch with this code already exists.") from exc
    ctx.audit(
        db,
        "branch.created",
        "branch",
        branch.id,
        branch_id=branch.id,
        details={"name": branch.name, "branch_code": branch.branch_code},
    )
    db.commit()
    return branch


@router.get("/{branch_id}", response_model=BranchRead)
def read_branch(
    branch_id: uuid.UUID,
    ctx: Annotated[TenantContext, Depends(require("branches.read"))],
    db: DB,
) -> object:
    return get_branch(db, branch_id)


@router.patch("/{branch_id}", response_model=BranchRead)
def update_branch(
    branch_id: uuid.UUID,
    data: BranchUpdate,
    ctx: Annotated[TenantContext, Depends(require("branches.manage"))],
    db: DB,
) -> object:
    branch = get_branch(db, branch_id)
    if not ctx.has_in_branch("branches.manage", branch.id):
        raise deny(ctx, "branches.manage", "branch")

    changes = data.model_dump(mode="json", exclude_unset=True)
    before = {key: getattr(branch, key) for key in changes}
    for key, value in changes.items():
        setattr(branch, key, value)
    ctx.audit(
        db,
        "branch.updated",
        "branch",
        branch.id,
        branch_id=branch.id,
        details={"before": before, "after": changes},
    )
    db.commit()
    return branch
