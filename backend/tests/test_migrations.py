"""Every migration must apply and roll back cleanly, so a failed deploy can be reverted."""

import os

import psycopg
from alembic import command
from alembic.config import Config

from tests.conftest import (
    ADMIN_DSN,
    OWNER_PASSWORD,
    OWNER_ROLE,
    _host_part,
)

DB = "clinicflow_test_migrations"
HERE = os.path.dirname(__file__)


def test_upgrade_downgrade_round_trip() -> None:
    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{DB}" OWNER {OWNER_ROLE}')
    admin_db = ADMIN_DSN.rsplit("/", 1)[0] + f"/{DB}"
    with psycopg.connect(admin_db, autocommit=True) as conn:
        conn.execute(f"ALTER SCHEMA public OWNER TO {OWNER_ROLE}")

    cfg = Config(os.path.join(HERE, "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(HERE, "..", "migrations"))
    cfg.set_main_option(
        "sqlalchemy.url",
        f"postgresql+psycopg://{OWNER_ROLE}:{OWNER_PASSWORD}@{_host_part}/{DB}",
    )
    try:
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        with psycopg.connect(admin_db) as conn:
            left = conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
                " AND tablename <> 'alembic_version'"
            ).fetchall()
        assert left == []
        command.upgrade(cfg, "head")
    finally:
        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
