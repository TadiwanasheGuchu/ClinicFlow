"""Physiotherapy extension service.

Core permissions apply (credential-gated): clinical.read to view, clinical.write to open,
update and discharge episodes, link sessions and record measurements, in the episode's
branch. Audit entries carry identifiers and counts only.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, NotFound, ValidationFailed
from app.core.tenancy import TenantContext
from app.modules.clinical import service as clinical
from app.modules.clinical.models import Encounter
from app.modules.physio.models import MEASURES, Episode, EpisodeSession, Measurement
from app.modules.physio.schemas import (
    Discharge,
    EpisodeCreate,
    EpisodeDetail,
    EpisodeRead,
    EpisodeWrite,
    MeasurementBatch,
    MeasurementRead,
    Series,
    SessionRead,
)
from app.shared.modules import require_module

MODULE = "physiotherapy"


def gate(ctx: TenantContext) -> None:
    require_module(ctx, MODULE)


def _today(ctx: TenantContext):  # type: ignore[no-untyped-def]
    return datetime.now(ZoneInfo(ctx.organisation.timezone)).date()


def get_episode(
    db: Session, ctx: TenantContext, episode_id: uuid.UUID, *, lock: bool = False
) -> Episode:
    episode = db.get(Episode, episode_id, with_for_update=lock or None)
    if episode is None:
        raise NotFound("Episode of care not found.")
    clinical.require_in_branch(ctx, "clinical.read", episode.branch_id)
    return episode


def _writable(ctx: TenantContext, episode: Episode) -> None:
    clinical.require_in_branch(ctx, "clinical.write", episode.branch_id)
    if episode.status != "active":
        raise Conflict("This episode of care has been discharged.", code="discharged")


def open_episode(db: Session, ctx: TenantContext, data: EpisodeCreate) -> Episode:
    clinical.require_in_branch(ctx, "clinical.write", data.branch_id)
    patient = clinical.get_patient(db, data.patient_id)
    episode = Episode(
        organisation_id=ctx.organisation_id,
        patient_id=patient.id,
        branch_id=data.branch_id,
        status="active",
        started_on=data.started_on or _today(ctx),
        clinician_user_id=ctx.user_id,
        **data.model_dump(exclude={"patient_id", "branch_id", "started_on"}),
    )
    db.add(episode)
    db.flush()
    ctx.audit(
        db,
        "physio_episode.opened",
        "physio_episode",
        episode.id,
        branch_id=episode.branch_id,
        details={"patient_id": str(patient.id)},
    )
    return episode


def update_episode(db: Session, ctx: TenantContext, episode: Episode, data: EpisodeWrite) -> None:
    _writable(ctx, episode)
    for key, value in data.model_dump().items():
        setattr(episode, key, value)
    ctx.audit(
        db, "physio_episode.updated", "physio_episode", episode.id, branch_id=episode.branch_id
    )


def _encounter_for(db: Session, episode: Episode, encounter_id: uuid.UUID) -> Encounter:
    encounter = db.get(Encounter, encounter_id)
    if encounter is None or encounter.patient_id != episode.patient_id:
        raise ValidationFailed("The consultation belongs to a different patient.")
    return encounter


def link_session(db: Session, ctx: TenantContext, episode: Episode, encounter_id: uuid.UUID) -> int:
    """Count a consultation as the next session. Linking twice is harmless."""
    _writable(ctx, episode)
    encounter = _encounter_for(db, episode, encounter_id)
    existing = db.scalar(
        select(EpisodeSession).where(
            EpisodeSession.episode_id == episode.id, EpisodeSession.encounter_id == encounter.id
        )
    )
    if existing is not None:
        return existing.session_number
    number = (
        db.scalar(
            select(func.max(EpisodeSession.session_number)).where(
                EpisodeSession.episode_id == episode.id
            )
        )
        or 0
    ) + 1
    db.add(
        EpisodeSession(
            organisation_id=ctx.organisation_id,
            episode_id=episode.id,
            encounter_id=encounter.id,
            session_number=number,
            linked_at=datetime.now(UTC),
        )
    )
    db.flush()
    ctx.audit(
        db,
        "physio_episode.session_linked",
        "physio_episode",
        episode.id,
        branch_id=episode.branch_id,
        details={"encounter_id": str(encounter.id), "session": number},
    )
    return number


def record_measurements(
    db: Session, ctx: TenantContext, episode: Episode, batch: MeasurementBatch
) -> None:
    _writable(ctx, episode)
    link_session(db, ctx, episode, batch.encounter_id)
    now = datetime.now(UTC)
    for m in batch.items:
        unit, low, high = MEASURES[m.measure]
        if not (low <= m.value <= high):
            raise ValidationFailed(f"{m.label}: enter a value from {low} to {high}.")
        if m.measure == "custom":
            unit = (m.unit or "").strip()
        db.add(
            Measurement(
                organisation_id=ctx.organisation_id,
                episode_id=episode.id,
                encounter_id=batch.encounter_id,
                measure=m.measure,
                label=m.label,
                side=m.side,
                value=m.value,
                unit=unit,
                measured_at=now,
                status="recorded",
                recorded_by=ctx.user_id,
            )
        )
    db.flush()
    ctx.audit(
        db,
        "physio_episode.measured",
        "physio_episode",
        episode.id,
        branch_id=episode.branch_id,
        details={"measurements": len(batch.items)},
    )


def measurement_error(
    db: Session, ctx: TenantContext, measurement_id: uuid.UUID, reason: str
) -> Episode:
    m = db.get(Measurement, measurement_id, with_for_update=True)
    if m is None:
        raise NotFound("Measurement not found.")
    episode = get_episode(db, ctx, m.episode_id)
    clinical.require_in_branch(ctx, "clinical.write", episode.branch_id)
    if m.status != "recorded":
        raise Conflict("This measurement is already marked as entered in error.")
    m.status, m.status_reason = "entered_in_error", reason
    ctx.audit(
        db,
        "physio_episode.measurement_error",
        "physio_episode",
        episode.id,
        branch_id=episode.branch_id,
        details={"measurement_id": str(m.id)},
    )
    return episode


def discharge(db: Session, ctx: TenantContext, episode: Episode, data: Discharge) -> None:
    _writable(ctx, episode)
    when = data.discharged_on or _today(ctx)
    if when < episode.started_on:
        raise ValidationFailed("Discharge can't be before the episode started.")
    episode.status, episode.discharged_on = "discharged", when
    episode.discharge_outcome, episode.discharge_summary = data.outcome, data.summary
    ctx.audit(
        db,
        "physio_episode.discharged",
        "physio_episode",
        episode.id,
        branch_id=episode.branch_id,
        details={"outcome": data.outcome},
    )


def _counts(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not ids:
        return {}
    return dict(
        db.execute(
            select(EpisodeSession.episode_id, func.count())
            .where(EpisodeSession.episode_id.in_(ids))
            .group_by(EpisodeSession.episode_id)
        ).all()
    )


def episode_reads(db: Session, rows: list[Episode]) -> list[EpisodeRead]:
    counts = _counts(db, [e.id for e in rows])
    names = clinical.user_names(db, {e.clinician_user_id for e in rows})
    return [
        EpisodeRead.model_validate(
            {
                **{
                    k: getattr(e, k)
                    for k in EpisodeRead.model_fields
                    if k not in ("sessions_done", "clinician_name")
                },
                "sessions_done": counts.get(e.id, 0),
                "clinician_name": names.get(e.clinician_user_id, ""),
            }
        )
        for e in rows
    ]


def detail(db: Session, episode: Episode) -> EpisodeDetail:
    base = episode_reads(db, [episode])[0]
    sessions = db.execute(
        select(EpisodeSession, Encounter)
        .join(Encounter, Encounter.id == EpisodeSession.encounter_id)
        .where(EpisodeSession.episode_id == episode.id)
        .order_by(EpisodeSession.session_number)
    ).all()
    rows = list(
        db.scalars(
            select(Measurement)
            .where(Measurement.episode_id == episode.id)
            .order_by(Measurement.measured_at, Measurement.label)
        )
    )
    names = clinical.user_names(
        db, {r.recorded_by for r in rows} | {enc.clinician_user_id for _, enc in sessions}
    )
    reads = [
        MeasurementRead.model_validate(
            {
                **{
                    k: getattr(r, k)
                    for k in MeasurementRead.model_fields
                    if k != "recorded_by_name"
                },
                "recorded_by_name": names.get(r.recorded_by, ""),
            }
        )
        for r in rows
    ]
    grouped: dict[tuple, list[MeasurementRead]] = {}  # type: ignore[type-arg]
    for r in reads:
        if r.status == "recorded":
            grouped.setdefault((r.measure, r.label.strip().lower(), r.side, r.unit), []).append(r)
    series = [
        Series(
            measure=points[0].measure,
            label=points[0].label,
            side=points[0].side,
            unit=points[0].unit,
            first=points[0].value,
            latest=points[-1].value,
            change=Decimal(points[-1].value - points[0].value),
            points=points,
        )
        for points in grouped.values()
    ]
    return EpisodeDetail(
        **base.model_dump(),
        sessions=[
            SessionRead(
                session_number=s.session_number,
                encounter_id=enc.id,
                started_at=enc.started_at,
                clinician_name=names.get(enc.clinician_user_id, ""),
            )
            for s, enc in sessions
        ],
        series=series,
        measurements=reads,
    )
