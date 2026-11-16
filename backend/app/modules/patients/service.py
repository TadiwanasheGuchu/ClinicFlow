import re
import uuid
from datetime import date, datetime

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, NotFound
from app.core.tenancy import TenantContext
from app.modules.organisations.schemas import OrganisationSettings
from app.modules.patients.models import Patient
from app.modules.patients.schemas import PatientCreate, PatientSummary
from app.shared.counters import format_number, next_value


def get_patient(db: Session, patient_id: uuid.UUID) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise NotFound("Patient not found.")
    return patient


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def find_duplicates(db: Session, data: PatientCreate) -> list[Patient]:
    """Likely duplicates: same ID number; or same date of birth with a matching surname,
    first name or phone number."""
    conditions = [
        and_(
            Patient.date_of_birth == data.date_of_birth,
            or_(
                func.lower(Patient.last_name) == data.last_name.lower(),
                func.lower(Patient.first_name) == data.first_name.lower(),
                *(
                    [func.regexp_replace(Patient.phone, r"\D", "", "g") == _digits(data.phone)]
                    if _digits(data.phone)
                    else []
                ),
            ),
        )
    ]
    if data.id_number:
        conditions.append(func.lower(Patient.id_number) == data.id_number.lower())
    return list(db.scalars(select(Patient).where(or_(*conditions)).limit(10)))


def register(db: Session, ctx: TenantContext, data: PatientCreate) -> Patient:
    if not data.confirm_not_duplicate:
        duplicates = find_duplicates(db, data)
        if duplicates:
            raise Conflict(
                "This person may already be registered. Review the matches, or confirm this "
                "is a different person.",
                code="possible_duplicate",
                details={
                    "candidates": [
                        PatientSummary.model_validate(p).model_dump(mode="json") for p in duplicates
                    ]
                },
            )
    settings = OrganisationSettings.model_validate(ctx.organisation.settings or {})
    number = format_number(
        settings.patient_number_prefix, next_value(db, ctx.organisation_id, "patient")
    )
    patient = Patient(
        organisation_id=ctx.organisation_id,
        patient_number=number,
        status="active",
        created_by=ctx.user_id,
        **data.model_dump(mode="json", exclude={"confirm_not_duplicate", "date_of_birth"}),
        date_of_birth=data.date_of_birth,
    )
    if patient.emergency_contact is None:
        patient.emergency_contact = {}
    db.add(patient)
    db.flush()
    return patient


def _parse_date(text: str) -> date | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def search(query: Select, q: str | None) -> Select:
    """Match patient number, date of birth, phone digits or every name token."""
    if not q or not q.strip():
        return query
    q = q.strip()
    if (dob := _parse_date(q)) is not None:
        return query.where(Patient.date_of_birth == dob)
    digits = _digits(q)
    if len(digits) >= 5 and not re.search(r"[A-Za-z]", q):
        return query.where(func.regexp_replace(Patient.phone, r"\D", "", "g").contains(digits))
    conditions = [func.upper(Patient.patient_number) == q.upper()]
    tokens = [t for t in re.split(r"[\s,]+", q) if t]
    conditions.append(
        and_(
            *(
                or_(Patient.first_name.ilike(f"{t}%"), Patient.last_name.ilike(f"{t}%"))
                for t in tokens
            )
        )
    )
    return query.where(or_(*conditions))
