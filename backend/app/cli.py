"""Operational commands. Run with the schema-owner database URL.

python -m app.cli sync-permissions
python -m app.cli grant-platform-admin someone@example.com
python -m app.cli check-db-roles      # refuse to run if a runtime role can bypass RLS
"""

import argparse
import sys

from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core import audit
from app.core.config import get_settings
from app.core.permissions import PERMISSIONS
from app.modules.roles.models import Permission
from app.modules.users.models import User


def _session() -> Session:
    return Session(create_engine(get_settings().migration_database_url))


def sync_permissions() -> None:
    """Upsert the permission catalogue from app.core.permissions. Safe to run on every deploy."""
    with _session() as db:
        for p in PERMISSIONS:
            stmt = insert(Permission).values(
                code=p.code, description=p.description, privileged=p.privileged
            )
            db.execute(
                stmt.on_conflict_do_update(
                    index_elements=[Permission.code],
                    set_={"description": p.description, "privileged": p.privileged},
                )
            )
        db.commit()
    print(f"Synchronised {len(PERMISSIONS)} permissions.")


def grant_platform_admin(email: str) -> None:
    with _session() as db:
        result = db.execute(
            update(User)
            .where(func.lower(User.email) == email.lower())
            .values(is_platform_admin=True)
        )
        if result.rowcount == 0:
            sys.exit(f"No user with email {email}. They must sign in once first.")
        user_id = db.scalar(select(User.id).where(func.lower(User.email) == email.lower()))
        audit.record(
            db,
            action="platform.admin_granted",
            resource_type="user",
            resource_id=user_id,
            organisation_id=None,
            actor_user_id=None,
            details={"via": "cli"},
        )
        db.commit()
    print(f"Granted platform administration to user {user_id}.")


def check_db_roles() -> None:
    """Row-Level Security is defence in depth only if neither the API's role nor the
    migration role can bypass it. Hosted Postgres consoles often create privileged roles;
    stop the deployment rather than run with one."""
    settings = get_settings()
    problems = []
    for label, url in (
        ("app", settings.database_url),
        ("migration", settings.migration_database_url),
    ):
        with create_engine(url).connect() as conn:
            name, superuser, bypass = conn.execute(
                text(
                    "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles"
                    " WHERE rolname = current_user"
                )
            ).one()
        if superuser or bypass:
            problems.append(f"{label} role {name!r} is a superuser or has BYPASSRLS")
    if problems:
        sys.exit("Unsafe database roles: " + "; ".join(problems))
    print("Database roles are subject to row-level security.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="clinicflow")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync-permissions")
    grant = sub.add_parser("grant-platform-admin")
    grant.add_argument("email")
    sub.add_parser("check-db-roles")
    args = parser.parse_args()
    if args.command == "sync-permissions":
        sync_permissions()
    elif args.command == "grant-platform-admin":
        grant_platform_admin(args.email)
    elif args.command == "check-db-roles":
        check_db_roles()


if __name__ == "__main__":
    main()
