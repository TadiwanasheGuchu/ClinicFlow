"""Authentication: verify OpenID Connect access tokens and resolve the local user."""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.config import Settings, get_settings
from app.core.db import get_db, set_scope
from app.core.exceptions import Forbidden, Unauthenticated
from app.modules.users.models import User

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)
_LAST_LOGIN_RESOLUTION = timedelta(minutes=5)


@dataclass(frozen=True)
class TokenClaims:
    sub: str
    email: str | None
    email_verified: bool
    name: str | None
    acr: str | None
    raw: dict[str, Any]


class TokenVerifier:
    """Validates signature, issuer, audience and expiry of an access token."""

    def __init__(self, settings: Settings, jwks_client: jwt.PyJWKClient | None = None) -> None:
        self._settings = settings
        self._jwks = jwks_client or jwt.PyJWKClient(settings.jwks_url, cache_keys=True)

    def verify(self, token: str) -> TokenClaims:
        try:
            key = self._jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=self._settings.oidc_algorithms,
                audience=self._settings.oidc_audience,
                issuer=self._settings.oidc_issuer,
                options={"require": ["exp", "iat", "sub", "iss"]},
                leeway=30,
            )
        except jwt.PyJWTError as exc:
            logger.info("Rejected access token: %s", exc.__class__.__name__)
            raise Unauthenticated("Invalid or expired access token.") from exc
        ns = self._settings.oidc_claim_namespace

        def claim(name: str):  # type: ignore[no-untyped-def]
            return claims.get(f"{ns}{name}") if ns and f"{ns}{name}" in claims else claims.get(name)

        return TokenClaims(
            sub=str(claims["sub"]),
            email=(claim("email") or "").strip().lower() or None,
            email_verified=bool(claim("email_verified") or False),
            name=claim("name"),
            acr=claims.get("acr"),
            raw=claims,
        )


@lru_cache
def get_token_verifier() -> TokenVerifier:
    return TokenVerifier(get_settings())


@dataclass
class CurrentUser:
    user: User
    claims: TokenClaims

    @property
    def id(self) -> uuid.UUID:
        return self.user.id


def _resolve_user(db: Session, claims: TokenClaims) -> User:
    user = db.scalar(select(User).where(User.identity_provider_id == claims.sub))
    if user is not None:
        return user

    if not claims.email or not claims.email_verified:
        raise Forbidden(
            "A verified email address is required to use ClinicFlow.", code="email_unverified"
        )

    user = db.scalar(select(User).where(func.lower(User.email) == claims.email))
    if user is not None:
        if user.identity_provider_id is not None:
            # The email belongs to a different identity. Never merge silently.
            raise Forbidden(
                "This email address is linked to another account.", code="identity_conflict"
            )
        # First sign-in of an invited user: link the identity to the invitation.
        user.identity_provider_id = claims.sub
        audit.record(
            db,
            action="user.identity_linked",
            resource_type="user",
            resource_id=user.id,
            organisation_id=None,
            actor_user_id=user.id,
        )
        return user

    user = User(
        identity_provider_id=claims.sub,
        email=claims.email,
        full_name=claims.name or claims.email,
        status="active",
        is_platform_admin=False,
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        action="user.registered",
        resource_type="user",
        resource_id=user.id,
        organisation_id=None,
        actor_user_id=user.id,
    )
    return user


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise Unauthenticated("Authentication required.")
    claims = verifier.verify(credentials.credentials)
    user = _resolve_user(db, claims)
    if user.status != "active":
        raise Forbidden("This account is suspended.", code="account_suspended")

    now = datetime.now(UTC)
    if user.last_login_at is None or now - user.last_login_at > _LAST_LOGIN_RESOLUTION:
        user.last_login_at = now
    if db.new or db.dirty:
        # Persist identity linking / last-login independently of the request outcome.
        db.commit()
    set_scope(db, user_id=user.id)
    return CurrentUser(user=user, claims=claims)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
