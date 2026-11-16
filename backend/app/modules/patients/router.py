import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.tenancy import TenantContext, require
from app.modules.patients import service
from app.modules.patients.models import Patient
from app.modules.patients.schemas import PatientCreate, PatientRead, PatientSummary, PatientUpdate
from app.shared.schemas import Page, PageParams

router = APIRouter(prefix="/patients", tags=["patients"])
DB = Annotated[Session, Depends(get_db)]
CanRead = Annotated[TenantContext, Depends(require("patients.read"))]
CanWrite = Annotated[TenantContext, Depends(require("patients.write"))]


@router.get("", response_model=Page[PatientSummary])
def list_patients(
    ctx: CanRead,
    db: DB,
    page: Annotated[PageParams, Depends()],
    q: Annotated[str | None, Query(max_length=100)] = None,
    status_filter: Annotated[Literal["active", "inactive"] | None, Query(alias="status")] = None,
) -> object:
    query = service.search(select(Patient), q)
    if status_filter:
        query = query.where(Patient.status == status_filter)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(func.lower(Patient.last_name), func.lower(Patient.first_name))
        .limit(page.limit)
        .offset(page.offset)
    ).all()
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.post("", response_model=PatientRead, status_code=status.HTTP_201_CREATED)
def register_patient(data: PatientCreate, ctx: CanWrite, db: DB) -> object:
    patient = service.register(db, ctx, data)
    ctx.audit(
        db,
        "patient.registered",
        "patient",
        patient.id,
        details={
            "patient_number": patient.patient_number,
            "confirmed_not_duplicate": data.confirm_not_duplicate,
        },
    )
    db.commit()
    return patient


@router.get("/{patient_id}", response_model=PatientRead)
def read_patient(patient_id: uuid.UUID, ctx: CanRead, db: DB) -> object:
    patient = service.get_patient(db, patient_id)
    ctx.audit(db, "patient.viewed", "patient", patient.id)
    db.commit()
    return patient


@router.patch("/{patient_id}", response_model=PatientRead)
def update_patient(patient_id: uuid.UUID, data: PatientUpdate, ctx: CanWrite, db: DB) -> object:
    patient = service.get_patient(db, patient_id)
    changes = data.model_dump(mode="json", exclude_unset=True)
    if "date_of_birth" in changes:
        changes["date_of_birth"] = data.date_of_birth
    if "emergency_contact" in changes and changes["emergency_contact"] is None:
        changes["emergency_contact"] = {}
    # Record which fields changed, not their values (keeps personal data out of the log).
    changed_fields = sorted(k for k, v in changes.items() if getattr(patient, k) != v)
    for key, value in changes.items():
        setattr(patient, key, value)
    ctx.audit(db, "patient.updated", "patient", patient.id, details={"fields": changed_fields})
    db.commit()
    return patient
