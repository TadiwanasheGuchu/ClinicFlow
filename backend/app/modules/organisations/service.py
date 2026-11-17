import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.db import set_scope
from app.core.permissions import OWNER_ROLE_KEY, ROLE_TEMPLATES
from app.core.security import CurrentUser
from app.modules.branches.models import Branch
from app.modules.members.models import Membership, MembershipRole
from app.modules.organisations.models import Organisation
from app.modules.organisations.schemas import OrganisationCreate, OrganisationSettings
from app.modules.portal import slugs
from app.modules.roles.models import Permission, Role, RolePermission


def register_organisation(
    db: Session, current: CurrentUser, data: OrganisationCreate
) -> Organisation:
    """Create an organisation with default roles and a first branch; the caller becomes Owner."""
    organisation_id = uuid.uuid4()
    set_scope(db, organisation_id=organisation_id, user_id=current.id)

    organisation = Organisation(
        id=organisation_id,
        name=data.name,
        legal_name=data.legal_name,
        registration_number=data.registration_number,
        email=data.email,
        phone=data.phone,
        currency="NAD",
        timezone=data.timezone,
        status="active",
        settings=OrganisationSettings().model_dump(),
        created_by=current.id,
    )
    db.add(organisation)
    db.flush()
    slugs.assign_unique(db, organisation_id, data.name)

    permission_ids = dict(db.execute(select(Permission.code, Permission.id)).all())
    roles: dict[str, Role] = {}
    for template in ROLE_TEMPLATES:
        role = Role(
            organisation_id=organisation_id,
            name=template.name,
            description=template.description,
            template_key=template.key,
            is_system=template.key == OWNER_ROLE_KEY,
        )
        db.add(role)
        db.flush()
        db.add_all(
            RolePermission(
                role_id=role.id,
                permission_id=permission_ids[code],
                organisation_id=organisation_id,
            )
            for code in sorted(template.permissions)
        )
        roles[template.key] = role

    branch = Branch(
        organisation_id=organisation_id,
        name=data.first_branch_name,
        branch_code=data.first_branch_code,
        operating_hours={},
        is_active=True,
    )
    membership = Membership(
        organisation_id=organisation_id,
        user_id=current.id,
        status="active",
        accepted_at=datetime.now(UTC),
    )
    db.add_all([branch, membership])
    db.flush()
    db.add(
        MembershipRole(
            organisation_id=organisation_id,
            membership_id=membership.id,
            role_id=roles[OWNER_ROLE_KEY].id,
            branch_id=None,
        )
    )

    audit.record(
        db,
        action="organisation.registered",
        resource_type="organisation",
        resource_id=organisation_id,
        organisation_id=organisation_id,
        actor_user_id=current.id,
        details={"name": data.name, "first_branch_id": str(branch.id)},
    )
    db.flush()
    return organisation
