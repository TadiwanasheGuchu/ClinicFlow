"""Import every model so Alembic and the metadata see the full schema."""

from app.modules.audit.models import AuditLog
from app.modules.branches.models import Branch
from app.modules.members.models import Membership, MembershipRole
from app.modules.organisations.models import Organisation
from app.modules.roles.models import Permission, Role, RolePermission
from app.modules.users.models import User

__all__ = [
    "AuditLog",
    "Branch",
    "Membership",
    "MembershipRole",
    "Organisation",
    "Permission",
    "Role",
    "RolePermission",
    "User",
]
