"""Permission catalogue and default role templates.

Code checks permission codes, never role names. Roles are per-organisation and
configurable; the templates below are created for every new organisation.
Clinical permissions are deliberately absent from Owner and Administrator:
running a practice does not imply access to clinical records.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionDef:
    code: str
    description: str
    privileged: bool = False


PERMISSIONS: tuple[PermissionDef, ...] = (
    # Platform foundation (Phase 1)
    PermissionDef("organisation.read", "View organisation details and settings"),
    PermissionDef("organisation.manage", "Edit organisation details and settings", True),
    PermissionDef("branches.read", "View branches"),
    PermissionDef("branches.manage", "Create and edit branches"),
    PermissionDef("members.read", "View staff members and their roles"),
    PermissionDef("members.manage", "Invite, suspend and assign roles to staff", True),
    PermissionDef("roles.read", "View roles and their permissions"),
    PermissionDef("roles.manage", "Create and edit roles", True),
    PermissionDef("audit.read", "View the audit log", True),
    # Phase 2 (patients and scheduling) and later phases.
    PermissionDef("patients.read", "View patient demographic records"),
    PermissionDef("patients.write", "Register and edit patients"),
    PermissionDef("appointments.read", "View appointments and calendars"),
    PermissionDef("appointments.manage", "Book, reschedule and cancel appointments"),
    PermissionDef(
        "appointments.override",
        "Override scheduling rules (double-booking, outside availability)",
        True,
    ),
    PermissionDef(
        "scheduling.manage", "Manage appointment types, practitioners and their availability"
    ),
    PermissionDef("credentials.verify", "Verify staff professional registration", True),
    PermissionDef("clinical.read", "View clinical records"),
    PermissionDef("clinical.write", "Write clinical notes and observations"),
    PermissionDef("clinical.sign", "Sign clinical records"),
    PermissionDef(
        "prescriptions.issue",
        "Issue prescriptions (also requires verified professional registration)",
    ),
    PermissionDef("billing.read", "View invoices and payments"),
    PermissionDef("billing.manage", "Create and issue invoices and record payments"),
    PermissionDef("billing.adjust", "Issue credit notes and refunds, and reverse payments", True),
    PermissionDef("medical_aid.manage", "Prepare and track medical aid claims"),
    PermissionDef("reports.operational", "View operational reports"),
    PermissionDef("reports.financial", "View financial reports"),
    # Phase 6: laboratory.
    PermissionDef("lab.read", "View laboratory orders and results"),
    PermissionDef(
        "lab.process", "Record specimen collection, laboratory progress and results"
    ),
    PermissionDef("lab.configure", "Manage the laboratory test list and laboratories"),
)

PERMISSION_CODES: frozenset[str] = frozenset(p.code for p in PERMISSIONS)
PRIVILEGED_PERMISSIONS: frozenset[str] = frozenset(p.code for p in PERMISSIONS if p.privileged)

# Clinical permissions take effect only for staff whose professional registration is
# verified and current (see app.core.tenancy); holding the role alone is not enough.
CLINICAL_PERMISSIONS: frozenset[str] = frozenset(
    {
        "clinical.read",
        "clinical.write",
        "clinical.sign",
        "prescriptions.issue",
        "lab.read",
        "lab.process",
    }
)
_CLINICAL = CLINICAL_PERMISSIONS


@dataclass(frozen=True)
class RoleTemplate:
    key: str
    name: str
    description: str
    permissions: frozenset[str]


OWNER_ROLE_KEY = "owner"

ROLE_TEMPLATES: tuple[RoleTemplate, ...] = (
    RoleTemplate(
        OWNER_ROLE_KEY,
        "Owner",
        "Full administrative and financial control of the organisation.",
        PERMISSION_CODES - _CLINICAL,
    ),
    RoleTemplate(
        "administrator",
        "Administrator",
        "Manages organisation settings, branches, staff and roles.",
        frozenset(
            {
                "organisation.read",
                "organisation.manage",
                "branches.read",
                "branches.manage",
                "members.read",
                "members.manage",
                "roles.read",
                "roles.manage",
                "audit.read",
                "patients.read",
                "appointments.read",
                "billing.read",
                "reports.operational",
                "scheduling.manage",
                "credentials.verify",
                "lab.configure",
            }
        ),
    ),
    RoleTemplate(
        "branch_manager",
        "Branch manager",
        "Runs day-to-day operations of a branch.",
        frozenset(
            {
                "organisation.read",
                "branches.read",
                "branches.manage",
                "members.read",
                "patients.read",
                "patients.write",
                "appointments.read",
                "appointments.manage",
                "appointments.override",
                "scheduling.manage",
                "reports.operational",
            }
        ),
    ),
    RoleTemplate(
        "practice_manager",
        "Practice manager",
        "Oversees practice performance and finances.",
        frozenset(
            {
                "billing.adjust",
                "organisation.read",
                "branches.read",
                "members.read",
                "appointments.read",
                "billing.read",
                "reports.operational",
                "reports.financial",
            }
        ),
    ),
    RoleTemplate(
        "receptionist",
        "Receptionist",
        "Registers patients, manages bookings and check-in.",
        frozenset(
            {
                "billing.manage",
                "organisation.read",
                "branches.read",
                "patients.read",
                "patients.write",
                "appointments.read",
                "appointments.manage",
                "billing.read",
            }
        ),
    ),
    RoleTemplate(
        "practitioner",
        "Practitioner",
        "Doctor, dentist, physiotherapist or other treating clinician.",
        frozenset(
            {
                "organisation.read",
                "branches.read",
                "patients.read",
                "patients.write",
                "appointments.read",
                "appointments.manage",
                "clinical.read",
                "clinical.write",
                "clinical.sign",
                "prescriptions.issue",
                "lab.read",
                "lab.process",
            }
        ),
    ),
    RoleTemplate(
        "nurse",
        "Nurse",
        "Records observations and assists with consultations.",
        frozenset(
            {
                "organisation.read",
                "branches.read",
                "patients.read",
                "appointments.read",
                "clinical.read",
                "clinical.write",
                "lab.read",
                "lab.process",
            }
        ),
    ),
    RoleTemplate(
        "lab_technician",
        "Laboratory technician",
        "Records specimen collection and laboratory results. No access to clinical notes.",
        frozenset(
            {
                "organisation.read",
                "branches.read",
                "patients.read",
                "lab.read",
                "lab.process",
            }
        ),
    ),
    RoleTemplate(
        "billing_officer",
        "Billing officer",
        "Manages invoices, payments and medical aid claims.",
        frozenset(
            {
                "billing.adjust",
                "organisation.read",
                "branches.read",
                "patients.read",
                "billing.read",
                "billing.manage",
                "medical_aid.manage",
                "reports.financial",
            }
        ),
    ),
    RoleTemplate(
        "auditor",
        "Auditor",
        "Read-only access to configuration and the audit log.",
        frozenset(
            {"organisation.read", "branches.read", "members.read", "roles.read", "audit.read"}
        ),
    ),
)

for _template in ROLE_TEMPLATES:
    assert _template.permissions <= PERMISSION_CODES, _template.key
