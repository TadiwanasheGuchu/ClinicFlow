"""Clinical records service.

Permissions (all credential-gated, see app.core.tenancy):
  clinical.read          view clinical data (every view is audited)
  clinical.write         start consultations, draft notes, record vitals, allergies,
                         diagnoses and referrals
  clinical.sign          sign one's own notes
  prescriptions.issue    issue and cancel prescriptions
Audit entries carry identifiers and types only — never clinical content — because the
audit log is readable by roles without clinical access.
"""

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, Forbidden, NotFound, ValidationFailed
from app.core.tenancy import TenantContext, deny
from app.modules.appointments import service as appointments
from app.modules.appointments.models import Appointment
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
from app.modules.clinical.schemas import (
    OBSERVATION_TYPES,
    AllergyRead,
    AllergySummary,
    EncounterCreate,
    PrescriptionCreate,
    PrescriptionItemRead,
    PrescriptionRead,
)
from app.modules.patients.models import Patient
from app.modules.staff.models import StaffProfile
from app.modules.users.models import User
from app.shared.counters import format_number, next_value


def require_in_branch(ctx: TenantContext, permission: str, branch_id: uuid.UUID) -> None:
    if not ctx.has_in_branch(permission, branch_id):
        raise deny(ctx, permission, "clinical_record")


def get_patient(db: Session, patient_id: uuid.UUID) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise NotFound("Patient not found.")
    return patient


def get_encounter(db: Session, ctx: TenantContext, encounter_id: uuid.UUID) -> Encounter:
    encounter = db.get(Encounter, encounter_id)
    if encounter is None:
        raise NotFound("Consultation not found.")
    require_in_branch(ctx, "clinical.read", encounter.branch_id)
    return encounter


def open_for_writing(ctx: TenantContext, encounter: Encounter) -> None:
    require_in_branch(ctx, "clinical.write", encounter.branch_id)
    if encounter.status != "open":
        raise Conflict(
            "This consultation is closed. Signed notes can still be amended.",
            code="encounter_closed",
        )


def log_view(
    db: Session,
    ctx: TenantContext,
    patient_id: uuid.UUID,
    what: str,
    resource_id: uuid.UUID | None = None,
) -> None:
    ctx.audit(
        db,
        "clinical_record.viewed",
        "patient",
        patient_id,
        details={"view": what, **({"resource_id": str(resource_id)} if resource_id else {})},
    )


# --- Encounters ------------------------------------------------------------------------


def start_encounter(db: Session, ctx: TenantContext, data: EncounterCreate) -> Encounter:
    patient = get_patient(db, data.patient_id)
    if patient.status != "active":
        raise ValidationFailed("This patient record is inactive.")
    appointment: Appointment | None = None
    branch_id = data.branch_id
    if data.appointment_id:
        appointment = appointments.get_appointment(db, data.appointment_id)
        if appointment.patient_id != patient.id:
            raise ValidationFailed("The appointment belongs to a different patient.")
        branch_id = appointment.branch_id
        existing = db.scalar(select(Encounter).where(Encounter.appointment_id == appointment.id))
        if existing is not None:
            raise Conflict(
                "A consultation already exists for this appointment.",
                code="encounter_exists",
                details={"encounter_id": str(existing.id)},
            )
        if appointment.status not in ("checked_in", "waiting", "in_consultation"):
            raise Conflict(
                "Check the patient in before starting the consultation.", code="not_checked_in"
            )
    assert branch_id is not None
    require_in_branch(ctx, "clinical.write", branch_id)
    encounter = Encounter(
        organisation_id=ctx.organisation_id,
        branch_id=branch_id,
        patient_id=patient.id,
        appointment_id=appointment.id if appointment else None,
        encounter_type=data.encounter_type,
        status="open",
        clinician_user_id=ctx.user_id,
        started_at=datetime.now(UTC),
    )
    db.add(encounter)
    db.flush()
    if appointment is not None and appointment.status != "in_consultation":
        previous = appointment.status
        appointment.status = "in_consultation"
        appointments.record_event(
            db,
            ctx,
            appointment,
            "status_changed",
            previous_status=previous,
            reason="Consultation started",
        )
    ctx.audit(
        db,
        "encounter.started",
        "encounter",
        encounter.id,
        branch_id=branch_id,
        details={"patient_id": str(patient.id), "encounter_type": data.encounter_type},
    )
    return encounter


def close_encounter(db: Session, ctx: TenantContext, encounter: Encounter) -> None:
    open_for_writing(ctx, encounter)
    drafts = db.scalar(
        select(func.count())
        .select_from(ClinicalNote)
        .where(ClinicalNote.encounter_id == encounter.id, ClinicalNote.status == "draft")
    )
    if drafts:
        raise Conflict(
            "Sign or discard draft notes before closing the consultation.", code="unsigned_notes"
        )
    signed = db.scalar(
        select(func.count())
        .select_from(ClinicalNote)
        .where(ClinicalNote.encounter_id == encounter.id)
    )
    if not signed:
        raise Conflict("Record at least one signed note before closing.", code="no_notes")
    encounter.status = "closed"
    encounter.ended_at = datetime.now(UTC)
    if encounter.appointment_id:
        appointment = db.get(Appointment, encounter.appointment_id)
        if appointment is not None and appointment.status == "in_consultation":
            appointment.status = "completed"
            appointments.record_event(
                db,
                ctx,
                appointment,
                "status_changed",
                previous_status="in_consultation",
                reason="Consultation closed",
            )
    ctx.audit(
        db,
        "encounter.closed",
        "encounter",
        encounter.id,
        branch_id=encounter.branch_id,
        details={"patient_id": str(encounter.patient_id)},
    )


# --- Notes -----------------------------------------------------------------------------


def _hash(note: ClinicalNote) -> str:
    payload = json.dumps(
        {
            "patient": str(note.patient_id),
            "group": str(note.note_group_id),
            "version": note.version_number,
            "type": note.note_type,
            "content": note.content,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def get_note(db: Session, ctx: TenantContext, note_id: uuid.UUID) -> tuple[ClinicalNote, Encounter]:
    note = db.get(ClinicalNote, note_id)
    if note is None:
        raise NotFound("Note not found.")
    return note, get_encounter(db, ctx, note.encounter_id)


def create_note(
    db: Session, ctx: TenantContext, encounter: Encounter, note_type: str, content: dict[str, str]
) -> ClinicalNote:
    open_for_writing(ctx, encounter)
    note = ClinicalNote(
        organisation_id=ctx.organisation_id,
        encounter_id=encounter.id,
        patient_id=encounter.patient_id,
        note_group_id=uuid.uuid4(),
        version_number=1,
        status="draft",
        note_type=note_type,
        content=content,
        author_user_id=ctx.user_id,
    )
    db.add(note)
    db.flush()
    ctx.audit(
        db,
        "clinical_note.created",
        "clinical_note",
        note.id,
        branch_id=encounter.branch_id,
        details={"patient_id": str(encounter.patient_id), "note_type": note_type},
    )
    return note


def _own_draft(ctx: TenantContext, note: ClinicalNote) -> None:
    if note.status != "draft":
        raise Conflict("Signed notes cannot be edited. Create an amendment.", code="note_signed")
    if note.author_user_id != ctx.user_id:
        raise Forbidden("Only the author can change a draft note.", code="not_author")


def update_draft(
    db: Session,
    ctx: TenantContext,
    note: ClinicalNote,
    encounter: Encounter,
    note_type: str,
    content: dict[str, str],
) -> None:
    require_in_branch(ctx, "clinical.write", encounter.branch_id)
    _own_draft(ctx, note)
    if note.version_number == 1 and encounter.status != "open":
        raise Conflict("This consultation is closed.", code="encounter_closed")
    note.note_type = note_type
    note.content = content
    ctx.audit(
        db,
        "clinical_note.draft_saved",
        "clinical_note",
        note.id,
        branch_id=encounter.branch_id,
        details={"patient_id": str(note.patient_id)},
    )


def discard_draft(
    db: Session, ctx: TenantContext, note: ClinicalNote, encounter: Encounter
) -> None:
    require_in_branch(ctx, "clinical.write", encounter.branch_id)
    _own_draft(ctx, note)
    ctx.audit(
        db,
        "clinical_note.discarded",
        "clinical_note",
        note.id,
        branch_id=encounter.branch_id,
        details={"patient_id": str(note.patient_id)},
    )
    db.delete(note)


def sign(db: Session, ctx: TenantContext, note: ClinicalNote, encounter: Encounter) -> None:
    require_in_branch(ctx, "clinical.sign", encounter.branch_id)
    _own_draft(ctx, note)
    if not any(v.strip() for v in note.content.values()):
        raise ValidationFailed("An empty note cannot be signed.")
    now = datetime.now(UTC)
    note.status = "signed"
    note.signed_at = now
    note.content_sha256 = _hash(note)
    db.flush()
    if note.amends_note_id:
        previous = db.get_one(ClinicalNote, note.amends_note_id)
        previous.status = "amended"
    ctx.audit(
        db,
        "clinical_note.signed",
        "clinical_note",
        note.id,
        branch_id=encounter.branch_id,
        details={
            "patient_id": str(note.patient_id),
            "version": note.version_number,
            "sha256": note.content_sha256,
            **({"amends": str(note.amends_note_id)} if note.amends_note_id else {}),
        },
    )


def amend(
    db: Session,
    ctx: TenantContext,
    note: ClinicalNote,
    encounter: Encounter,
    note_type: str,
    content: dict[str, str],
    reason: str,
) -> ClinicalNote:
    """Create a new draft version of a signed note. The original stays unchanged."""
    require_in_branch(ctx, "clinical.write", encounter.branch_id)
    if note.status != "signed":
        raise Conflict(
            "Only the current signed version of a note can be amended.", code="not_current_version"
        )
    pending = db.scalar(
        select(ClinicalNote).where(
            ClinicalNote.note_group_id == note.note_group_id, ClinicalNote.status == "draft"
        )
    )
    if pending is not None:
        raise Conflict(
            "An amendment to this note is already in progress.",
            code="amendment_pending",
            details={"note_id": str(pending.id)},
        )
    amendment = ClinicalNote(
        organisation_id=ctx.organisation_id,
        encounter_id=note.encounter_id,
        patient_id=note.patient_id,
        note_group_id=note.note_group_id,
        version_number=note.version_number + 1,
        status="draft",
        note_type=note_type,
        content=content,
        author_user_id=ctx.user_id,
        amends_note_id=note.id,
        amendment_reason=reason,
    )
    db.add(amendment)
    db.flush()
    ctx.audit(
        db,
        "clinical_note.amendment_started",
        "clinical_note",
        amendment.id,
        branch_id=encounter.branch_id,
        details={"patient_id": str(note.patient_id), "amends": str(note.id)},
    )
    return amendment


# --- Allergies -------------------------------------------------------------------------


def allergy_summary(db: Session, patient_id: uuid.UUID) -> AllergySummary:
    active = db.scalars(
        select(Allergy)
        .where(Allergy.patient_id == patient_id, Allergy.status == "active")
        .order_by(Allergy.substance)
    ).all()
    if active:
        return AllergySummary(
            state="has_allergies", allergies=[AllergyRead.model_validate(a) for a in active]
        )
    assessment = db.get(AllergyAssessment, patient_id)
    if assessment is not None and assessment.no_known_allergies:
        return AllergySummary(
            state="no_known_allergies", allergies=[], assessed_at=assessment.recorded_at
        )
    return AllergySummary(state="not_recorded", allergies=[])


def require_clinical_anywhere(ctx: TenantContext, permission: str) -> None:
    """Patient-level safety data (allergies) is not tied to a branch."""
    if not ctx.has(permission):
        raise deny(ctx, permission, "clinical_record")


def record_allergy(db: Session, ctx: TenantContext, patient: Patient, data: Any) -> Allergy:
    require_clinical_anywhere(ctx, "clinical.write")
    allergy = Allergy(
        organisation_id=ctx.organisation_id,
        patient_id=patient.id,
        substance=data.substance,
        reaction=data.reaction,
        severity=data.severity,
        status="active",
        recorded_by=ctx.user_id,
    )
    db.add(allergy)
    assessment = db.get(AllergyAssessment, patient.id)
    if assessment is not None:
        assessment.no_known_allergies = False
        assessment.recorded_by = ctx.user_id
        assessment.recorded_at = datetime.now(UTC)
    db.flush()
    ctx.audit(
        db,
        "allergy.recorded",
        "allergy",
        allergy.id,
        details={"patient_id": str(patient.id), "severity": data.severity},
    )
    return allergy


def record_no_known_allergies(db: Session, ctx: TenantContext, patient: Patient) -> None:
    require_clinical_anywhere(ctx, "clinical.write")
    if db.scalar(
        select(Allergy.id)
        .where(Allergy.patient_id == patient.id, Allergy.status == "active")
        .limit(1)
    ):
        raise Conflict("The patient has active allergies recorded.", code="has_allergies")
    assessment = db.get(AllergyAssessment, patient.id)
    now = datetime.now(UTC)
    if assessment is None:
        db.add(
            AllergyAssessment(
                organisation_id=ctx.organisation_id,
                patient_id=patient.id,
                no_known_allergies=True,
                recorded_by=ctx.user_id,
                recorded_at=now,
            )
        )
    else:
        assessment.no_known_allergies, assessment.recorded_by, assessment.recorded_at = (
            True,
            ctx.user_id,
            now,
        )
    ctx.audit(db, "allergy.no_known_allergies_recorded", "patient", patient.id)


# --- Observations, diagnoses, referrals -----------------------------------------------


def record_observations(
    db: Session, ctx: TenantContext, encounter: Encounter, data: Any
) -> list[Observation]:
    open_for_writing(ctx, encounter)
    measured_at = data.measured_at or datetime.now(UTC)
    rows = [
        Observation(
            organisation_id=ctx.organisation_id,
            encounter_id=encounter.id,
            patient_id=encounter.patient_id,
            observation_type=item.observation_type,
            value=item.value,
            unit=OBSERVATION_TYPES[item.observation_type][0],
            measured_at=measured_at,
            status="final",
            recorded_by=ctx.user_id,
        )
        for item in data.items
    ]
    db.add_all(rows)
    db.flush()
    ctx.audit(
        db,
        "observation.recorded",
        "encounter",
        encounter.id,
        branch_id=encounter.branch_id,
        details={
            "patient_id": str(encounter.patient_id),
            "types": sorted(i.observation_type for i in data.items),
        },
    )
    return rows


_ICD10 = re.compile(r"^[A-TV-Z][0-9][0-9AB](\.[0-9A-Z]{1,4})?$")


def record_diagnosis(db: Session, ctx: TenantContext, encounter: Encounter, data: Any) -> Diagnosis:
    open_for_writing(ctx, encounter)
    diagnosis = Diagnosis(
        organisation_id=ctx.organisation_id,
        encounter_id=encounter.id,
        patient_id=encounter.patient_id,
        code_system="icd10" if data.code else "none",
        code=data.code,
        description=data.description,
        clinical_status="active",
        onset_date=data.onset_date,
        recorded_by=ctx.user_id,
    )
    db.add(diagnosis)
    db.flush()
    ctx.audit(
        db,
        "diagnosis.recorded",
        "diagnosis",
        diagnosis.id,
        branch_id=encounter.branch_id,
        details={"patient_id": str(encounter.patient_id)},
    )
    return diagnosis


def issue_referral(db: Session, ctx: TenantContext, encounter: Encounter, data: Any) -> Referral:
    open_for_writing(ctx, encounter)
    referral = Referral(
        organisation_id=ctx.organisation_id,
        encounter_id=encounter.id,
        patient_id=encounter.patient_id,
        referring_user_id=ctx.user_id,
        receiving_provider=data.receiving_provider,
        receiving_specialty=data.receiving_specialty,
        urgency=data.urgency,
        reason=data.reason,
        status="issued",
    )
    db.add(referral)
    db.flush()
    ctx.audit(
        db,
        "referral.issued",
        "referral",
        referral.id,
        branch_id=encounter.branch_id,
        details={"patient_id": str(encounter.patient_id), "urgency": data.urgency},
    )
    return referral


# --- Prescriptions ---------------------------------------------------------------------


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t) >= 4}


def allergy_matches(db: Session, patient_id: uuid.UUID, items: list[Any]) -> list[dict[str, str]]:
    """Basic name check: a word of a recorded allergy appears in a medication name.
    It does not know drug classes or cross-reactions and is not an interaction database."""
    active = db.scalars(
        select(Allergy).where(Allergy.patient_id == patient_id, Allergy.status == "active")
    ).all()
    matches = []
    for item in items:
        med_tokens = _tokens(item.medication)
        for allergy in active:
            if _tokens(allergy.substance) & med_tokens:
                matches.append(
                    {
                        "medication": item.medication,
                        "allergy": allergy.substance,
                        "allergy_id": str(allergy.id),
                    }
                )
    return matches


def issue_prescription(
    db: Session, ctx: TenantContext, encounter: Encounter, data: PrescriptionCreate
) -> Prescription:
    open_for_writing(ctx, encounter)
    require_in_branch(ctx, "prescriptions.issue", encounter.branch_id)
    matches = allergy_matches(db, encounter.patient_id, data.items)
    if matches and not data.acknowledge_allergy_warning:
        raise Conflict(
            "Possible allergy: "
            + "; ".join(f"{m['medication']} — recorded allergy to {m['allergy']}" for m in matches),
            code="allergy_warning",
            details={"matches": matches},
        )
    profile = db.scalar(select(StaffProfile).where(StaffProfile.membership_id == ctx.membership.id))
    if profile is None or not profile.professional_number:
        raise Forbidden("Your professional registration must be recorded to prescribe.")
    user = db.get_one(User, ctx.user_id)
    prescription = Prescription(
        organisation_id=ctx.organisation_id,
        encounter_id=encounter.id,
        patient_id=encounter.patient_id,
        prescription_number=format_number(
            "RX", next_value(db, ctx.organisation_id, "prescription")
        ),
        prescriber_user_id=ctx.user_id,
        prescriber_name=user.full_name,
        prescriber_registration=" ".join(
            filter(None, [profile.registration_body, profile.professional_number])
        ),
        status="issued",
        issued_at=datetime.now(UTC),
        allergy_warning=(
            {
                "matches": matches,
                "acknowledged_by": str(ctx.user_id),
                "reason": data.acknowledgement_reason,
            }
            if matches
            else None
        ),
    )
    db.add(prescription)
    db.flush()
    db.add_all(
        PrescriptionItem(
            organisation_id=ctx.organisation_id,
            prescription_id=prescription.id,
            position=i + 1,
            **item.model_dump(),
        )
        for i, item in enumerate(data.items)
    )
    db.flush()
    ctx.audit(
        db,
        "prescription.issued",
        "prescription",
        prescription.id,
        branch_id=encounter.branch_id,
        details={
            "patient_id": str(encounter.patient_id),
            "number": prescription.prescription_number,
            "items": len(data.items),
            "allergy_warning_overridden": bool(matches),
        },
    )
    return prescription


def cancel_prescription(
    db: Session, ctx: TenantContext, prescription: Prescription, encounter: Encounter, reason: str
) -> None:
    require_in_branch(ctx, "prescriptions.issue", encounter.branch_id)
    if prescription.status != "issued":
        raise Conflict("This prescription is already cancelled.")
    prescription.status = "cancelled"
    prescription.cancelled_at = datetime.now(UTC)
    prescription.cancel_reason = reason
    ctx.audit(
        db,
        "prescription.cancelled",
        "prescription",
        prescription.id,
        branch_id=encounter.branch_id,
        details={
            "patient_id": str(prescription.patient_id),
            "number": prescription.prescription_number,
        },
    )


def prescription_reads(db: Session, rows: list[Prescription]) -> list[PrescriptionRead]:
    if not rows:
        return []
    items: dict[uuid.UUID, list[PrescriptionItem]] = {}
    for item in db.scalars(
        select(PrescriptionItem)
        .where(PrescriptionItem.prescription_id.in_([r.id for r in rows]))
        .order_by(PrescriptionItem.position)
    ):
        items.setdefault(item.prescription_id, []).append(item)
    return [
        PrescriptionRead.model_validate(
            {
                **{k: getattr(r, k) for k in PrescriptionRead.model_fields if k != "items"},
                "items": [PrescriptionItemRead.model_validate(i) for i in items.get(r.id, [])],
            }
        )
        for r in rows
    ]


def user_names(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    return dict(db.execute(select(User.id, User.full_name).where(User.id.in_(ids))).all())
