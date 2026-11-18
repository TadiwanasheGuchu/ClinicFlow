"""Physiotherapy extension: episodes of care, linked sessions and outcome measures.

The clinical narrative of each session stays in the core consultation notes (signed and
versioned there). Measurements are never edited, only marked entered in error, and a
discharged episode is closed (migration 0008 triggers).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey

# measure: (unit, minimum, maximum)
MEASURES: dict[str, tuple[str, Decimal, Decimal]] = {
    "pain_nrs": ("/10", Decimal(0), Decimal(10)),  # numeric pain rating scale
    "psfs": ("/10", Decimal(0), Decimal(10)),  # patient-specific functional scale
    "rom": ("°", Decimal(0), Decimal(360)),  # range of movement
    "strength_mrc": ("/5", Decimal(0), Decimal(5)),  # MRC muscle strength grade
    "custom": ("", Decimal(-100000), Decimal(100000)),
}
OUTCOMES = ("goals_met", "partly_met", "not_met", "self_discharged", "referred_on")


def _same_org(column: str, target: str, name: str) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        ["organisation_id", column], [f"{target}.organisation_id", f"{target}.id"], name=name
    )


class Episode(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "physio_episodes"
    __table_args__ = (
        UniqueConstraint("organisation_id", "id", name="uq_physio_episodes_org_id"),
        _same_org("patient_id", "patients", "fk_physio_episodes_patient_same_org"),
        _same_org("branch_id", "branches", "fk_physio_episodes_branch_same_org"),
        CheckConstraint("status IN ('active','discharged')", name="ck_physio_episode_status"),
        CheckConstraint(
            "discharge_outcome IS NULL OR discharge_outcome IN ("
            + ",".join(f"'{o}'" for o in OUTCOMES)
            + ")",
            name="ck_physio_outcome",
        ),
        CheckConstraint(
            "planned_sessions IS NULL OR planned_sessions BETWEEN 1 AND 200",
            name="ck_physio_planned_sessions",
        ),
        Index("ix_physio_episodes_org_patient", "organisation_id", "patient_id"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column()
    branch_id: Mapped[uuid.UUID] = mapped_column()
    condition: Mapped[str] = mapped_column(String(200))
    body_region: Mapped[str | None] = mapped_column(String(100))
    referral_source: Mapped[str | None] = mapped_column(String(200))
    goals: Mapped[str | None] = mapped_column(Text)
    planned_sessions: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    started_on: Mapped[date] = mapped_column(Date)
    clinician_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    discharged_on: Mapped[date | None] = mapped_column(Date)
    discharge_outcome: Mapped[str | None] = mapped_column(String(30))
    discharge_summary: Mapped[str | None] = mapped_column(Text)


class EpisodeSession(UUIDPrimaryKey, Base):
    """A consultation counted as a session of an episode."""

    __tablename__ = "physio_episode_sessions"
    __table_args__ = (
        UniqueConstraint("episode_id", "encounter_id"),
        UniqueConstraint("episode_id", "session_number"),
        _same_org("episode_id", "physio_episodes", "fk_physio_sessions_episode_same_org"),
        _same_org("encounter_id", "encounters", "fk_physio_sessions_encounter_same_org"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    episode_id: Mapped[uuid.UUID] = mapped_column(index=True)
    encounter_id: Mapped[uuid.UUID] = mapped_column(index=True)
    session_number: Mapped[int] = mapped_column(Integer)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Measurement(UUIDPrimaryKey, Base):
    __tablename__ = "physio_measurements"
    __table_args__ = (
        _same_org("episode_id", "physio_episodes", "fk_physio_measure_episode_same_org"),
        _same_org("encounter_id", "encounters", "fk_physio_measure_encounter_same_org"),
        CheckConstraint(
            "measure IN (" + ",".join(f"'{m}'" for m in MEASURES) + ")",
            name="ck_physio_measure",
        ),
        CheckConstraint("side IS NULL OR side IN ('left','right','both')", name="ck_physio_side"),
        CheckConstraint(
            "status IN ('recorded','entered_in_error')", name="ck_physio_measure_status"
        ),
        Index("ix_physio_measure_episode_time", "episode_id", "measured_at"),
    )

    organisation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organisations.id"))
    episode_id: Mapped[uuid.UUID] = mapped_column()
    encounter_id: Mapped[uuid.UUID] = mapped_column()
    measure: Mapped[str] = mapped_column(String(20))
    # What was measured, e.g. "Shoulder flexion" or a PSFS activity.
    label: Mapped[str] = mapped_column(String(150))
    side: Mapped[str | None] = mapped_column(String(10))
    value: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    unit: Mapped[str] = mapped_column(String(20))
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20))
    status_reason: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
