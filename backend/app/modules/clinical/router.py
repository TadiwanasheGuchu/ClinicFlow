import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import Conflict, NotFound
from app.core.tenancy import TenantContext, require
from app.modules.branches.models import Branch
from app.modules.clinical import service
from app.modules.clinical.models import (
    Allergy,
    ClinicalNote,
    Diagnosis,
    Encounter,
    Observation,
    Prescription,
    Referral,
)
from app.modules.clinical.schemas import (
    AllergyCreate,
    AllergyRead,
    AllergyStatusChange,
    AllergySummary,
    Amendment,
    ClinicalSummary,
    DiagnosisCreate,
    DiagnosisRead,
    DiagnosisStatusChange,
    EncounterCreate,
    EncounterDetail,
    EncounterRead,
    LatestObservation,
    NoteRead,
    NoteWrite,
    ObservationBatch,
    ObservationRead,
    PrescriptionCreate,
    PrescriptionRead,
    ReferralCreate,
    ReferralRead,
    StatusReason,
)

router = APIRouter(tags=["clinical records"])
DB = Annotated[Session, Depends(get_db)]
Reader = Annotated[TenantContext, Depends(require("clinical.read"))]
Writer = Annotated[TenantContext, Depends(require("clinical.write"))]
Signer = Annotated[TenantContext, Depends(require("clinical.sign"))]
Prescriber = Annotated[TenantContext, Depends(require("prescriptions.issue"))]


def _encounter_reads(db: Session, rows: list[Encounter]) -> list[EncounterRead]:
    names = service.user_names(db, {e.clinician_user_id for e in rows})
    branches = (
        dict(
            db.execute(
                select(Branch.id, Branch.name).where(Branch.id.in_({e.branch_id for e in rows}))
            ).all()
        )
        if rows
        else {}
    )
    return [
        EncounterRead.model_validate(
            {
                **{
                    k: getattr(e, k)
                    for k in EncounterRead.model_fields
                    if k not in ("clinician_name", "branch_name")
                },
                "clinician_name": names.get(e.clinician_user_id, ""),
                "branch_name": branches.get(e.branch_id, ""),
            }
        )
        for e in rows
    ]


def _note_reads(db: Session, rows: list[ClinicalNote]) -> list[NoteRead]:
    names = service.user_names(db, {n.author_user_id for n in rows})
    return [
        NoteRead.model_validate(
            {
                **{k: getattr(n, k) for k in NoteRead.model_fields if k != "author_name"},
                "author_name": names.get(n.author_user_id),
            }
        )
        for n in rows
    ]


def _detail(db: Session, encounter: Encounter) -> EncounterDetail:
    def rows(model, order):  # type: ignore[no-untyped-def]
        return list(
            db.scalars(select(model).where(model.encounter_id == encounter.id).order_by(order))
        )

    return EncounterDetail(
        **_encounter_reads(db, [encounter])[0].model_dump(),
        notes=_note_reads(db, rows(ClinicalNote, ClinicalNote.created_at)),
        observations=[
            ObservationRead.model_validate(o) for o in rows(Observation, Observation.measured_at)
        ],
        diagnoses=[DiagnosisRead.model_validate(d) for d in rows(Diagnosis, Diagnosis.created_at)],
        prescriptions=service.prescription_reads(db, rows(Prescription, Prescription.issued_at)),
        referrals=[ReferralRead.model_validate(r) for r in rows(Referral, Referral.created_at)],
    )


# --- Patient-level clinical summary ------------------------------------------------------


@router.get("/patients/{patient_id}/clinical-summary", response_model=ClinicalSummary)
def clinical_summary(patient_id: uuid.UUID, ctx: Reader, db: DB) -> object:
    patient = service.get_patient(db, patient_id)
    scope = ctx.branch_scope("clinical.read")
    encounters_q = select(Encounter).where(Encounter.patient_id == patient.id)
    if scope is not None:
        encounters_q = encounters_q.where(Encounter.branch_id.in_(scope))
    encounters = list(db.scalars(encounters_q.order_by(Encounter.started_at.desc()).limit(50)))
    visible = [e.id for e in encounters]

    diagnoses = db.scalars(
        select(Diagnosis)
        .where(
            Diagnosis.patient_id == patient.id,
            Diagnosis.clinical_status == "active",
            Diagnosis.encounter_id.in_(visible),
        )
        .order_by(Diagnosis.created_at.desc())
    ).all()
    latest: dict[str, Observation] = {}
    for obs in db.scalars(
        select(Observation)
        .where(
            Observation.patient_id == patient.id,
            Observation.status == "final",
            Observation.encounter_id.in_(visible),
        )
        .order_by(Observation.measured_at.desc())
    ):
        latest.setdefault(obs.observation_type, obs)
    since = datetime.now(UTC) - timedelta(days=180)
    prescriptions = db.scalars(
        select(Prescription)
        .where(
            Prescription.patient_id == patient.id,
            Prescription.issued_at >= since,
            Prescription.encounter_id.in_(visible),
        )
        .order_by(Prescription.issued_at.desc())
    ).all()
    service.log_view(db, ctx, patient.id, "summary")
    db.commit()
    return ClinicalSummary(
        patient_id=patient.id,
        allergies=service.allergy_summary(db, patient.id),
        active_diagnoses=[DiagnosisRead.model_validate(d) for d in diagnoses],
        latest_observations=[LatestObservation.model_validate(o) for o in latest.values()],
        recent_prescriptions=service.prescription_reads(db, list(prescriptions)),
        encounters=_encounter_reads(db, encounters),
    )


@router.get("/patients/{patient_id}/allergies", response_model=AllergySummary)
def allergies(patient_id: uuid.UUID, ctx: Reader, db: DB, include_inactive: bool = False) -> object:
    patient = service.get_patient(db, patient_id)
    summary = service.allergy_summary(db, patient.id)
    if include_inactive:
        summary.allergies = [
            AllergyRead.model_validate(a)
            for a in db.scalars(
                select(Allergy).where(Allergy.patient_id == patient.id).order_by(Allergy.created_at)
            )
        ]
    service.log_view(db, ctx, patient.id, "allergies")
    db.commit()
    return summary


@router.post(
    "/patients/{patient_id}/allergies",
    response_model=AllergyRead,
    status_code=status.HTTP_201_CREATED,
)
def add_allergy(patient_id: uuid.UUID, data: AllergyCreate, ctx: Writer, db: DB) -> object:
    allergy = service.record_allergy(db, ctx, service.get_patient(db, patient_id), data)
    db.commit()
    return allergy


@router.post("/patients/{patient_id}/allergies/none-known", response_model=AllergySummary)
def no_known_allergies(patient_id: uuid.UUID, ctx: Writer, db: DB) -> object:
    patient = service.get_patient(db, patient_id)
    service.record_no_known_allergies(db, ctx, patient)
    db.commit()
    return service.allergy_summary(db, patient.id)


@router.post("/allergies/{allergy_id}/status", response_model=AllergyRead)
def change_allergy(allergy_id: uuid.UUID, data: AllergyStatusChange, ctx: Writer, db: DB) -> object:
    allergy = db.get(Allergy, allergy_id)
    if allergy is None:
        raise NotFound("Allergy not found.")
    if allergy.status != "active":
        raise Conflict("Only active allergies can be changed.")
    allergy.status, allergy.status_reason = data.status, data.reason
    ctx.audit(
        db,
        "allergy.status_changed",
        "allergy",
        allergy.id,
        details={"patient_id": str(allergy.patient_id), "status": data.status},
    )
    db.commit()
    return allergy


# --- Encounters ----------------------------------------------------------------------------


@router.post("/encounters", response_model=EncounterDetail, status_code=status.HTTP_201_CREATED)
def start(data: EncounterCreate, ctx: Writer, db: DB) -> object:
    encounter = service.start_encounter(db, ctx, data)
    db.commit()
    return _detail(db, encounter)


@router.get("/encounters/{encounter_id}", response_model=EncounterDetail)
def read_encounter(encounter_id: uuid.UUID, ctx: Reader, db: DB) -> object:
    encounter = service.get_encounter(db, ctx, encounter_id)
    service.log_view(db, ctx, encounter.patient_id, "encounter", encounter.id)
    db.commit()
    return _detail(db, encounter)


@router.get("/appointments/{appointment_id}/encounter", response_model=EncounterRead)
def encounter_for_appointment(appointment_id: uuid.UUID, ctx: Reader, db: DB) -> object:
    encounter = db.scalar(select(Encounter).where(Encounter.appointment_id == appointment_id))
    if encounter is None:
        raise NotFound("No consultation for this appointment.")
    service.require_in_branch(ctx, "clinical.read", encounter.branch_id)
    return _encounter_reads(db, [encounter])[0]


@router.post("/encounters/{encounter_id}/close", response_model=EncounterDetail)
def close(encounter_id: uuid.UUID, ctx: Writer, db: DB) -> object:
    encounter = service.get_encounter(db, ctx, encounter_id)
    service.close_encounter(db, ctx, encounter)
    db.commit()
    return _detail(db, encounter)


# --- Notes ----------------------------------------------------------------------------------


@router.post(
    "/encounters/{encounter_id}/notes", response_model=NoteRead, status_code=status.HTTP_201_CREATED
)
def create_note(encounter_id: uuid.UUID, data: NoteWrite, ctx: Writer, db: DB) -> object:
    encounter = service.get_encounter(db, ctx, encounter_id)
    note = service.create_note(db, ctx, encounter, data.note_type, data.content)
    db.commit()
    return _note_reads(db, [note])[0]


@router.put("/notes/{note_id}", response_model=NoteRead)
def save_draft(note_id: uuid.UUID, data: NoteWrite, ctx: Writer, db: DB) -> object:
    note, encounter = service.get_note(db, ctx, note_id)
    service.update_draft(db, ctx, note, encounter, data.note_type, data.content)
    db.commit()
    return _note_reads(db, [note])[0]


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def discard(note_id: uuid.UUID, ctx: Writer, db: DB) -> Response:
    note, encounter = service.get_note(db, ctx, note_id)
    service.discard_draft(db, ctx, note, encounter)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/notes/{note_id}/sign", response_model=NoteRead)
def sign(note_id: uuid.UUID, ctx: Signer, db: DB) -> object:
    note, encounter = service.get_note(db, ctx, note_id)
    service.sign(db, ctx, note, encounter)
    db.commit()
    return _note_reads(db, [note])[0]


@router.post("/notes/{note_id}/amend", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def amend(note_id: uuid.UUID, data: Amendment, ctx: Writer, db: DB) -> object:
    note, encounter = service.get_note(db, ctx, note_id)
    amendment = service.amend(db, ctx, note, encounter, data.note_type, data.content, data.reason)
    db.commit()
    return _note_reads(db, [amendment])[0]


# --- Observations, diagnoses, referrals ------------------------------------------------------


@router.post(
    "/encounters/{encounter_id}/observations",
    response_model=list[ObservationRead],
    status_code=status.HTTP_201_CREATED,
)
def add_observations(
    encounter_id: uuid.UUID, data: ObservationBatch, ctx: Writer, db: DB
) -> object:
    encounter = service.get_encounter(db, ctx, encounter_id)
    rows = service.record_observations(db, ctx, encounter, data)
    db.commit()
    return rows


@router.post("/observations/{observation_id}/entered-in-error", response_model=ObservationRead)
def observation_error(observation_id: uuid.UUID, data: StatusReason, ctx: Writer, db: DB) -> object:
    obs = db.get(Observation, observation_id)
    if obs is None:
        raise NotFound("Observation not found.")
    encounter = service.get_encounter(db, ctx, obs.encounter_id)
    service.require_in_branch(ctx, "clinical.write", encounter.branch_id)
    if obs.status != "final":
        raise Conflict("Already marked as entered in error.")
    obs.status, obs.status_reason = "entered_in_error", data.reason
    ctx.audit(
        db,
        "observation.entered_in_error",
        "observation",
        obs.id,
        details={"patient_id": str(obs.patient_id)},
    )
    db.commit()
    return obs


@router.post(
    "/encounters/{encounter_id}/diagnoses",
    response_model=DiagnosisRead,
    status_code=status.HTTP_201_CREATED,
)
def add_diagnosis(encounter_id: uuid.UUID, data: DiagnosisCreate, ctx: Writer, db: DB) -> object:
    encounter = service.get_encounter(db, ctx, encounter_id)
    diagnosis = service.record_diagnosis(db, ctx, encounter, data)
    db.commit()
    return diagnosis


@router.post("/diagnoses/{diagnosis_id}/status", response_model=DiagnosisRead)
def diagnosis_status(
    diagnosis_id: uuid.UUID, data: DiagnosisStatusChange, ctx: Writer, db: DB
) -> object:
    diagnosis = db.get(Diagnosis, diagnosis_id)
    if diagnosis is None:
        raise NotFound("Diagnosis not found.")
    encounter = service.get_encounter(db, ctx, diagnosis.encounter_id)
    service.require_in_branch(ctx, "clinical.write", encounter.branch_id)
    if diagnosis.clinical_status == "entered_in_error":
        raise Conflict("A diagnosis entered in error cannot be changed.")
    diagnosis.clinical_status, diagnosis.status_reason = data.clinical_status, data.reason
    ctx.audit(
        db,
        "diagnosis.status_changed",
        "diagnosis",
        diagnosis.id,
        details={"patient_id": str(diagnosis.patient_id), "status": data.clinical_status},
    )
    db.commit()
    return diagnosis


@router.post(
    "/encounters/{encounter_id}/referrals",
    response_model=ReferralRead,
    status_code=status.HTTP_201_CREATED,
)
def add_referral(encounter_id: uuid.UUID, data: ReferralCreate, ctx: Writer, db: DB) -> object:
    encounter = service.get_encounter(db, ctx, encounter_id)
    referral = service.issue_referral(db, ctx, encounter, data)
    db.commit()
    return referral


@router.post("/referrals/{referral_id}/cancel", response_model=ReferralRead)
def cancel_referral(referral_id: uuid.UUID, data: StatusReason, ctx: Writer, db: DB) -> object:
    referral = db.get(Referral, referral_id)
    if referral is None:
        raise NotFound("Referral not found.")
    encounter = service.get_encounter(db, ctx, referral.encounter_id)
    service.require_in_branch(ctx, "clinical.write", encounter.branch_id)
    if referral.status != "issued":
        raise Conflict("This referral is already cancelled.")
    referral.status, referral.status_reason = "cancelled", data.reason
    ctx.audit(
        db,
        "referral.cancelled",
        "referral",
        referral.id,
        details={"patient_id": str(referral.patient_id)},
    )
    db.commit()
    return referral


# --- Prescriptions -------------------------------------------------------------------------


@router.post(
    "/encounters/{encounter_id}/prescriptions",
    response_model=PrescriptionRead,
    status_code=status.HTTP_201_CREATED,
)
def prescribe(encounter_id: uuid.UUID, data: PrescriptionCreate, ctx: Prescriber, db: DB) -> object:
    encounter = service.get_encounter(db, ctx, encounter_id)
    prescription = service.issue_prescription(db, ctx, encounter, data)
    db.commit()
    return service.prescription_reads(db, [prescription])[0]


def _prescription(
    db: Session, ctx: TenantContext, prescription_id: uuid.UUID
) -> tuple[Prescription, Encounter]:
    prescription = db.get(Prescription, prescription_id)
    if prescription is None:
        raise NotFound("Prescription not found.")
    return prescription, service.get_encounter(db, ctx, prescription.encounter_id)


@router.get("/prescriptions/{prescription_id}", response_model=PrescriptionRead)
def read_prescription(prescription_id: uuid.UUID, ctx: Reader, db: DB) -> object:
    prescription, _ = _prescription(db, ctx, prescription_id)
    service.log_view(db, ctx, prescription.patient_id, "prescription", prescription.id)
    db.commit()
    return service.prescription_reads(db, [prescription])[0]


@router.post("/prescriptions/{prescription_id}/cancel", response_model=PrescriptionRead)
def cancel_prescription(
    prescription_id: uuid.UUID, data: StatusReason, ctx: Prescriber, db: DB
) -> object:
    prescription, encounter = _prescription(db, ctx, prescription_id)
    service.cancel_prescription(db, ctx, prescription, encounter, data.reason)
    db.commit()
    return service.prescription_reads(db, [prescription])[0]
