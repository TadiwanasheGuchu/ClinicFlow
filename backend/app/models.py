"""Import every model so Alembic and the metadata see the full schema."""

from app.modules.appointments.models import Appointment, AppointmentEvent
from app.modules.audit.models import AuditLog
from app.modules.branches.models import Branch
from app.modules.clinical.models import (
    Allergy,
    AllergyAssessment,
    ClinicalNote,
    Diagnosis,
    Encounter,
    Observation,
    Prescription,
    PrescriptionItem,
    Referral,
)
from app.modules.members.models import Membership, MembershipRole
from app.modules.notifications.models import Notification
from app.modules.organisations.models import Organisation
from app.modules.patients.models import Patient
from app.modules.portal.models import OrganisationSlug, PatientAccount, PatientLinkCode
from app.modules.roles.models import Permission, Role, RolePermission
from app.modules.scheduling.models import (
    AppointmentType,
    Provider,
    ProviderAvailability,
    ProviderUnavailability,
)
from app.modules.staff.models import StaffProfile
from app.modules.users.models import User
from app.shared.counters import OrganisationCounter

__all__ = [
    "Allergy",
    "AllergyAssessment",
    "Appointment",
    "AppointmentEvent",
    "AppointmentType",
    "AuditLog",
    "Branch",
    "ClinicalNote",
    "Diagnosis",
    "Encounter",
    "Membership",
    "MembershipRole",
    "Notification",
    "Observation",
    "Organisation",
    "OrganisationCounter",
    "OrganisationSlug",
    "Patient",
    "PatientAccount",
    "PatientLinkCode",
    "Permission",
    "Prescription",
    "PrescriptionItem",
    "Provider",
    "ProviderAvailability",
    "ProviderUnavailability",
    "Referral",
    "Role",
    "RolePermission",
    "StaffProfile",
    "User",
]
