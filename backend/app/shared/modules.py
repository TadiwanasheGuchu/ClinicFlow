"""Optional specialty extensions are enabled per organisation (settings.specialty_modules).

The core clinical record never depends on them; their endpoints refuse to work for an
organisation that hasn't switched them on.
"""

from app.core.exceptions import Forbidden
from app.core.tenancy import TenantContext
from app.modules.organisations.schemas import OrganisationSettings


def enabled(ctx: TenantContext, module: str) -> bool:
    settings = OrganisationSettings.model_validate(ctx.organisation.settings or {})
    return module in settings.specialty_modules


def require_module(ctx: TenantContext, module: str) -> None:
    if not enabled(ctx, module):
        raise Forbidden(
            "This module is not switched on for your practice.", code="module_not_enabled"
        )
