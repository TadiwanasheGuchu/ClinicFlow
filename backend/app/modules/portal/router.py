import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.appointments.models import Appointment
from app.modules.branches.models import Branch
from app.modules.portal import service
from app.modules.portal.context import LinkedDep, PortalDep, PublicPortal, public_portal
from app.modules.portal.schemas import (
    LinkRequest,
    PortalAppointment,
    PortalBooking,
    PortalBranch,
    PortalCancel,
    PortalInfo,
    PortalMe,
    PortalPatient,
    PortalPolicy,
    PortalProfileUpdate,
    PortalProvider,
    PortalReschedule,
    PortalType,
    SelfRegistration,
)
from app.modules.scheduling import service as scheduling
from app.modules.scheduling.models import AppointmentType, Provider, ProviderAvailability
from app.modules.scheduling.schemas import Slot

router = APIRouter(prefix="/portal/{slug}", tags=["patient portal"])
DB = Annotated[Session, Depends(get_db)]


@router.get("", response_model=PortalInfo)
def portal_info(portal: Annotated[PublicPortal, Depends(public_portal)], db: DB) -> object:
    """Public practice information for the booking page (no sign-in required)."""
    org, s = portal.organisation, portal.settings
    branches = db.scalars(
        select(Branch).where(Branch.is_active.is_(True)).order_by(Branch.name)
    ).all()
    providers = []
    for p in db.scalars(
        select(Provider)
        .where(Provider.online_booking_enabled.is_(True))
        .order_by(Provider.display_name)
    ):
        if not scheduling.provider_bookable(db, p, org.timezone):
            continue
        branch_ids = sorted(
            set(
                db.scalars(
                    select(ProviderAvailability.branch_id).where(
                        ProviderAvailability.provider_id == p.id
                    )
                )
            ),
            key=str,
        )
        if branch_ids:
            profile = scheduling.provider_profile(db, p)
            providers.append(
                PortalProvider(
                    id=p.id,
                    display_name=p.display_name,
                    specialty=profile.specialty,
                    branch_ids=branch_ids,
                )
            )
    types = db.scalars(
        select(AppointmentType)
        .where(AppointmentType.online_bookable.is_(True), AppointmentType.is_active.is_(True))
        .order_by(AppointmentType.name)
    ).all()
    return PortalInfo(
        name=org.name,
        phone=org.phone,
        email=org.email,
        branches=[PortalBranch.model_validate(b) for b in branches],
        providers=providers,
        appointment_types=[PortalType.model_validate(t) for t in types],
        policy=PortalPolicy(
            min_notice_hours=s.online_min_notice_hours,
            max_days_ahead=s.online_max_days_ahead,
            cancel_cutoff_hours=s.online_cancel_cutoff_hours,
            auto_confirm=s.online_auto_confirm,
        ),
    )


@router.get("/me", response_model=PortalMe)
def me(ctx: PortalDep) -> object:
    return PortalMe(
        email=ctx.current.user.email,
        linked=ctx.patient is not None,
        patient=PortalPatient.model_validate(ctx.patient) if ctx.patient else None,
    )


@router.post("/register", response_model=PortalMe, status_code=status.HTTP_201_CREATED)
def register(data: SelfRegistration, ctx: PortalDep, db: DB) -> object:
    patient = service.register(db, ctx, data)
    db.commit()
    return PortalMe(
        email=ctx.current.user.email, linked=True, patient=PortalPatient.model_validate(patient)
    )


@router.post("/link", response_model=PortalMe)
def link(data: LinkRequest, ctx: PortalDep, db: DB) -> object:
    patient = service.link(db, ctx, data.code, data.date_of_birth)
    db.commit()
    return PortalMe(
        email=ctx.current.user.email, linked=True, patient=PortalPatient.model_validate(patient)
    )


@router.patch("/me", response_model=PortalMe)
def update_profile(data: PortalProfileUpdate, ctx: LinkedDep, db: DB) -> object:
    assert ctx.patient is not None
    changes = data.model_dump(mode="json", exclude_unset=True)
    for key, value in changes.items():
        setattr(ctx.patient, key, value)
    ctx.audit(db, "patient.updated", "patient", ctx.patient.id, details={"fields": sorted(changes)})
    db.commit()
    return PortalMe(
        email=ctx.current.user.email, linked=True, patient=PortalPatient.model_validate(ctx.patient)
    )


@router.get("/slots", response_model=list[Slot])
def slots(
    ctx: LinkedDep,
    db: DB,
    provider_id: uuid.UUID,
    branch_id: uuid.UUID,
    appointment_type_id: uuid.UUID,
    day: Annotated[date, Query(alias="date")],
) -> object:
    windows = service.slots(db, ctx, provider_id, branch_id, appointment_type_id, day)
    return [Slot(start_at=w.start, end_at=w.end) for w in windows]


@router.get("/appointments", response_model=list[PortalAppointment])
def my_appointments(ctx: LinkedDep, db: DB) -> object:
    assert ctx.patient is not None
    rows = db.scalars(
        select(Appointment)
        .where(Appointment.patient_id == ctx.patient.id)
        .order_by(Appointment.start_at.desc())
        .limit(100)
    ).all()
    return service.to_portal(db, ctx, list(rows))


@router.get("/appointments/{appointment_id}", response_model=PortalAppointment)
def my_appointment(appointment_id: uuid.UUID, ctx: LinkedDep, db: DB) -> object:
    return service.to_portal(db, ctx, [service.own_appointment(db, ctx, appointment_id)])[0]


@router.post("/appointments", response_model=PortalAppointment, status_code=status.HTTP_201_CREATED)
def book(data: PortalBooking, ctx: LinkedDep, db: DB) -> object:
    appointment = service.book(db, ctx, data)
    db.commit()
    return service.to_portal(db, ctx, [appointment])[0]


@router.post("/appointments/{appointment_id}/cancel", response_model=PortalAppointment)
def cancel(appointment_id: uuid.UUID, data: PortalCancel, ctx: LinkedDep, db: DB) -> object:
    appointment = service.own_appointment(db, ctx, appointment_id)
    service.cancel(db, ctx, appointment, data.reason)
    db.commit()
    return service.to_portal(db, ctx, [appointment])[0]


@router.post("/appointments/{appointment_id}/reschedule", response_model=PortalAppointment)
def reschedule(appointment_id: uuid.UUID, data: PortalReschedule, ctx: LinkedDep, db: DB) -> object:
    appointment = service.own_appointment(db, ctx, appointment_id)
    service.reschedule(db, ctx, appointment, data.start_at)
    db.commit()
    return service.to_portal(db, ctx, [appointment])[0]
