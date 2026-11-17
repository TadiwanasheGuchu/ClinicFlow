"""Test harness: a real PostgreSQL database (RLS must be exercised, not mocked) and
locally signed OIDC tokens."""

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pytest

ADMIN_DSN = os.environ.get(
    "TEST_ADMIN_DSN", "postgresql://postgres:postgres@localhost:5432/postgres"
)
TEST_DB = os.environ.get("TEST_DB_NAME", "clinicflow_test")
APP_ROLE, APP_PASSWORD = "clinicflow_app", "clinicflow_app"
# Schema owner: a dedicated non-superuser role, as in production (superusers bypass RLS).
OWNER_ROLE, OWNER_PASSWORD = "clinicflow_owner", "clinicflow_owner"
ISSUER = "https://auth.test/realms/clinicflow"
AUDIENCE = "clinicflow-api"

_host_part = ADMIN_DSN.split("@", 1)[1].rsplit("/", 1)[0]
OWNER_URL = f"postgresql://{OWNER_ROLE}:{OWNER_PASSWORD}@{_host_part}/{TEST_DB}"
os.environ.update(
    CLINICFLOW_ENVIRONMENT="test",
    CLINICFLOW_DATABASE_URL=f"postgresql+psycopg://{APP_ROLE}:{APP_PASSWORD}@{_host_part}/{TEST_DB}",
    CLINICFLOW_MIGRATION_DATABASE_URL=OWNER_URL.replace("postgresql://", "postgresql+psycopg://"),
    CLINICFLOW_OIDC_ISSUER=ISSUER,
    CLINICFLOW_OIDC_AUDIENCE=AUDIENCE,
    CLINICFLOW_OIDC_MFA_ACR_VALUES="[]",
)

import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.security import TokenVerifier, get_token_verifier  # noqa: E402

PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _StaticJWKS:
    def get_signing_key_from_jwt(self, token: str) -> Any:
        return type("Key", (), {"key": PRIVATE_KEY.public_key()})()


def make_token(
    sub: str,
    email: str | None,
    *,
    name: str = "Test User",
    email_verified: bool = True,
    acr: str | None = "1",
    key: Any = None,
    **overrides: Any,
) -> str:
    now = datetime.now(UTC)
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": sub,
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "email": email,
        "email_verified": email_verified,
        "name": name,
        "acr": acr,
        **overrides,
    }
    return jwt.encode(claims, key or PRIVATE_KEY, algorithm="RS256")


@pytest.fixture(scope="session", autouse=True)
def database() -> Iterator[None]:
    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
        for role, password in ((APP_ROLE, APP_PASSWORD), (OWNER_ROLE, OWNER_PASSWORD)):
            if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone():
                conn.execute(
                    f"CREATE ROLE {role} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '{password}'"
                )
        conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{TEST_DB}" OWNER {OWNER_ROLE}')
    with psycopg.connect(
        OWNER_URL.replace(OWNER_ROLE + ":" + OWNER_PASSWORD, "postgres:postgres"), autocommit=True
    ) as conn:
        conn.execute(f"ALTER SCHEMA public OWNER TO {OWNER_ROLE}")

    from alembic import command
    from alembic.config import Config

    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option(
        "script_location", os.path.join(os.path.dirname(__file__), "..", "migrations")
    )
    command.upgrade(cfg, "head")

    from app.cli import sync_permissions

    sync_permissions()
    yield


@pytest.fixture(scope="session")
def client(database: None) -> Iterator[TestClient]:
    from app.main import app

    app.dependency_overrides[get_token_verifier] = lambda: TokenVerifier(
        get_settings(),
        jwks_client=_StaticJWKS(),  # type: ignore[arg-type]
    )
    with TestClient(app) as c:
        yield c


@pytest.fixture
def owner_db() -> Iterator[psycopg.Connection]:
    """Direct connection as the schema owner (RLS is FORCED, so policies still apply)."""
    with psycopg.connect(OWNER_URL, autocommit=True) as conn:
        yield conn


@pytest.fixture
def app_db() -> Iterator[psycopg.Connection]:
    """Direct connection as the application role."""
    dsn = f"postgresql://{APP_ROLE}:{APP_PASSWORD}@{_host_part}/{TEST_DB}"
    with psycopg.connect(dsn, autocommit=True) as conn:
        yield conn


@dataclass
class Actor:
    client: TestClient
    email: str
    name: str = "Test User"
    sub: str = field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str | None = None

    def headers(self, org_id: str | None = None, **token_kwargs: Any) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {make_token(self.sub, self.email, name=self.name, **token_kwargs)}"
        }
        org = org_id or self.org_id
        if org:
            headers["X-Organisation-Id"] = org
        return headers

    def get(self, url: str, org_id: str | None = None, **kw: Any):  # type: ignore[no-untyped-def]
        return self.client.get(url, headers=self.headers(org_id), **kw)

    def post(self, url: str, json: Any = None, org_id: str | None = None):  # type: ignore[no-untyped-def]
        return self.client.post(url, json=json, headers=self.headers(org_id))

    def put(self, url: str, json: Any = None, org_id: str | None = None):  # type: ignore[no-untyped-def]
        return self.client.put(url, json=json, headers=self.headers(org_id))

    def patch(self, url: str, json: Any = None, org_id: str | None = None):  # type: ignore[no-untyped-def]
        return self.client.patch(url, json=json, headers=self.headers(org_id))

    def delete(self, url: str, org_id: str | None = None):  # type: ignore[no-untyped-def]
        return self.client.delete(url, headers=self.headers(org_id))


@pytest.fixture
def new_actor(client: TestClient):  # type: ignore[no-untyped-def]
    def factory(name: str = "Test User") -> Actor:
        return Actor(client=client, email=f"{uuid.uuid4().hex[:12]}@example.com", name=name)

    return factory


@pytest.fixture
def owner(new_actor):  # type: ignore[no-untyped-def]
    """A user who has registered an organisation (and is its Owner)."""
    actor: Actor = new_actor("Owner Person")
    response = actor.post("/api/v1/organisations", json={"name": f"Clinic {uuid.uuid4().hex[:6]}"})
    assert response.status_code == 201, response.text
    actor.org_id = response.json()["id"]
    return actor


def role_id(actor: Actor, template_key: str) -> str:
    roles = actor.get("/api/v1/roles").json()
    return next(r["id"] for r in roles if r["template_key"] == template_key)


def main_branch_id(actor: Actor) -> str:
    return actor.get("/api/v1/branches").json()["items"][0]["id"]


@pytest.fixture
def add_member(new_actor):  # type: ignore[no-untyped-def]
    """Invite a new user with the given role(s) into `inviter`'s organisation and accept."""

    def factory(inviter: Actor, *templates: str, branch_id: str | None = None) -> Actor:
        member: Actor = new_actor(f"{templates[0]} person")
        payload = {
            "email": member.email,
            "full_name": member.name,
            "roles": [{"role_id": role_id(inviter, t), "branch_id": branch_id} for t in templates],
        }
        response = inviter.post("/api/v1/members", json=payload)
        assert response.status_code == 201, response.text
        accepted = member.post(f"/api/v1/me/invitations/{inviter.org_id}/accept")
        assert accepted.status_code == 200, accepted.text
        member.org_id = inviter.org_id
        member.membership_id = response.json()["id"]  # type: ignore[attr-defined]
        return member

    return factory


# --- Phase 2 helpers ---------------------------------------------------------------

TZ = "Africa/Windhoek"


def local_time(days_ahead: int, hhmm: str) -> str:
    """ISO timestamp for a local wall-clock time `days_ahead` days from today."""
    from datetime import date, datetime, time
    from zoneinfo import ZoneInfo

    day = date.today() + timedelta(days=days_ahead)
    hour, minute = map(int, hhmm.split(":"))
    return datetime.combine(day, time(hour, minute), tzinfo=ZoneInfo(TZ)).isoformat()


def make_patient(
    actor: Actor, first: str = "Ndapandula", last: str | None = None, **extra: Any
) -> dict:
    payload = {
        "first_name": first,
        "last_name": last or f"Test{uuid.uuid4().hex[:6]}",
        "date_of_birth": "1990-04-12",
        "confirm_not_duplicate": True,
        **extra,
    }
    response = actor.post("/api/v1/patients", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def verify_practitioner(owner: Actor, member: Actor, *, expiry: str = "2099-12-31") -> None:
    profile = owner.put(
        f"/api/v1/members/{member.membership_id}/profile",
        json={
            "profession": "medical_practitioner",
            "specialty": "General practice",
            "registration_body": "HPCNA",
            "professional_number": f"MP{uuid.uuid4().hex[:6]}",
            "licence_expiry_date": expiry,
        },
    )
    assert profile.status_code == 200, profile.text
    verified = owner.post(
        f"/api/v1/members/{member.membership_id}/profile/verify",
        json={"decision": "verified", "note": "Checked HPCNA register"},
    )
    assert verified.status_code == 200, verified.text


@pytest.fixture
def clinic(owner, add_member):  # type: ignore[no-untyped-def]
    """An organisation with a verified practitioner working 08:00-17:00 every day at the
    main branch, a 30-minute consultation type (10-minute buffer) and a receptionist."""
    branch = main_branch_id(owner)
    doctor = add_member(owner, "practitioner")
    verify_practitioner(owner, doctor)
    provider = owner.post("/api/v1/providers", json={"membership_id": doctor.membership_id})
    assert provider.status_code == 201, provider.text
    provider_id = provider.json()["id"]
    windows = [
        {"branch_id": branch, "weekday": d, "start_time": "08:00", "end_time": "17:00"}
        for d in range(7)
    ]
    assert (
        owner.put(
            f"/api/v1/providers/{provider_id}/availability", json={"windows": windows}
        ).status_code
        == 200
    )
    appointment_type = owner.post(
        "/api/v1/appointment-types",
        json={
            "name": "Consultation",
            "duration_minutes": 30,
            "fee": "450.00",
            "booking_buffer_minutes": 10,
        },
    )
    assert appointment_type.status_code == 201, appointment_type.text
    receptionist = add_member(owner, "receptionist")
    return {
        "owner": owner,
        "doctor": doctor,
        "receptionist": receptionist,
        "branch_id": branch,
        "provider_id": provider_id,
        "type_id": appointment_type.json()["id"],
    }


def book(actor: Actor, clinic: dict, patient_id: str, start: str, **extra: Any):  # type: ignore[no-untyped-def]
    return actor.post(
        "/api/v1/appointments",
        json={
            "patient_id": patient_id,
            "provider_id": clinic["provider_id"],
            "branch_id": clinic["branch_id"],
            "appointment_type_id": clinic["type_id"],
            "start_at": start,
            **extra,
        },
    )


# --- Phase 3 helpers ---------------------------------------------------------------


@pytest.fixture
def portal(clinic):  # type: ignore[no-untyped-def]
    """`clinic` with the patient portal enabled and its practitioner and type bookable online."""
    owner = clinic["owner"]
    assert (
        owner.patch("/api/v1/organisation", json={"settings": {"portal_enabled": True}}).status_code
        == 200
    )
    assert (
        owner.patch(
            f"/api/v1/providers/{clinic['provider_id']}", json={"online_booking_enabled": True}
        ).status_code
        == 200
    )
    assert (
        owner.patch(
            f"/api/v1/appointment-types/{clinic['type_id']}", json={"online_bookable": True}
        ).status_code
        == 200
    )
    slug = owner.get("/api/v1/organisation").json()["slug"]
    return {**clinic, "slug": slug, "base": f"/api/v1/portal/{slug}"}


@pytest.fixture
def patient_user(new_actor, portal):  # type: ignore[no-untyped-def]
    """A signed-in patient who self-registered with the portal practice."""
    actor: Actor = new_actor("Portal Patient")
    response = actor.post(
        f"{portal['base']}/register",
        json={
            "first_name": "Selma",
            "last_name": f"Portal{uuid.uuid4().hex[:6]}",
            "date_of_birth": "1992-07-01",
            "phone": "+264 81 765 4321",
        },
    )
    assert response.status_code == 201, response.text
    return actor


def portal_book(actor: Actor, portal: dict, start: str):  # type: ignore[no-untyped-def]
    return actor.post(
        f"{portal['base']}/appointments",
        json={
            "provider_id": portal["provider_id"],
            "branch_id": portal["branch_id"],
            "appointment_type_id": portal["type_id"],
            "start_at": start,
        },
    )
