import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.tenancy import TenantContext, require
from app.modules.clinical import service as clinical
from app.modules.physio import service
from app.modules.physio.models import Episode
from app.modules.physio.schemas import (
    Discharge,
    EpisodeCreate,
    EpisodeDetail,
    EpisodeRead,
    EpisodeWrite,
    MeasurementBatch,
    Reason,
    SessionLink,
)

router = APIRouter(tags=["physiotherapy"])
DB = Annotated[Session, Depends(get_db)]


def _gated(permission: str):  # type: ignore[no-untyped-def]
    base = require(permission)

    def dependency(ctx: Annotated[TenantContext, Depends(base)]) -> TenantContext:
        service.gate(ctx)
        return ctx

    return dependency


Reader = Annotated[TenantContext, Depends(_gated("clinical.read"))]
Writer = Annotated[TenantContext, Depends(_gated("clinical.write"))]


@router.get("/patients/{patient_id}/physio-episodes", response_model=list[EpisodeRead])
def list_episodes(patient_id: uuid.UUID, ctx: Reader, db: DB) -> object:
    patient = clinical.get_patient(db, patient_id)
    query = select(Episode).where(Episode.patient_id == patient.id)
    scope = ctx.branch_scope("clinical.read")
    if scope is not None:
        query = query.where(Episode.branch_id.in_(scope))
    rows = list(db.scalars(query.order_by(Episode.status, Episode.started_on.desc())))
    clinical.log_view(db, ctx, patient.id, "physio_episodes")
    db.commit()
    return service.episode_reads(db, rows)


@router.post("/physio-episodes", response_model=EpisodeDetail, status_code=status.HTTP_201_CREATED)
def open_episode(data: EpisodeCreate, ctx: Writer, db: DB) -> object:
    episode = service.open_episode(db, ctx, data)
    db.commit()
    return service.detail(db, episode)


@router.get("/physio-episodes/{episode_id}", response_model=EpisodeDetail)
def read_episode(episode_id: uuid.UUID, ctx: Reader, db: DB) -> object:
    episode = service.get_episode(db, ctx, episode_id)
    clinical.log_view(db, ctx, episode.patient_id, "physio_episode", episode.id)
    db.commit()
    return service.detail(db, episode)


@router.put("/physio-episodes/{episode_id}", response_model=EpisodeDetail)
def update_episode(episode_id: uuid.UUID, data: EpisodeWrite, ctx: Writer, db: DB) -> object:
    episode = service.get_episode(db, ctx, episode_id, lock=True)
    service.update_episode(db, ctx, episode, data)
    db.commit()
    return service.detail(db, episode)


@router.post("/physio-episodes/{episode_id}/sessions", response_model=EpisodeDetail)
def link_session(episode_id: uuid.UUID, data: SessionLink, ctx: Writer, db: DB) -> object:
    episode = service.get_episode(db, ctx, episode_id, lock=True)
    service.link_session(db, ctx, episode, data.encounter_id)
    db.commit()
    return service.detail(db, episode)


@router.post(
    "/physio-episodes/{episode_id}/measurements",
    response_model=EpisodeDetail,
    status_code=status.HTTP_201_CREATED,
)
def measure(episode_id: uuid.UUID, data: MeasurementBatch, ctx: Writer, db: DB) -> object:
    episode = service.get_episode(db, ctx, episode_id, lock=True)
    service.record_measurements(db, ctx, episode, data)
    db.commit()
    return service.detail(db, episode)


@router.post("/physio-measurements/{measurement_id}/entered-in-error", response_model=EpisodeDetail)
def measurement_error(measurement_id: uuid.UUID, data: Reason, ctx: Writer, db: DB) -> object:
    episode = service.measurement_error(db, ctx, measurement_id, data.reason)
    db.commit()
    return service.detail(db, episode)


@router.post("/physio-episodes/{episode_id}/discharge", response_model=EpisodeDetail)
def discharge(episode_id: uuid.UUID, data: Discharge, ctx: Writer, db: DB) -> object:
    episode = service.get_episode(db, ctx, episode_id, lock=True)
    service.discharge(db, ctx, episode, data)
    db.commit()
    return service.detail(db, episode)
