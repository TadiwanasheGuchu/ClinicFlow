from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables (prefix CLINICFLOW_)."""

    model_config = SettingsConfigDict(env_prefix="CLINICFLOW_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "staging", "production"] = "development"

    # The application connects as a non-owner, non-superuser role so that
    # PostgreSQL Row-Level Security is always enforced.
    database_url: str = (
        "postgresql+psycopg://clinicflow_app:clinicflow_app@localhost:5432/clinicflow"
    )
    # Migrations run as the schema owner: a dedicated role, never a superuser
    # (superusers bypass RLS).
    migration_database_url: str = (
        "postgresql+psycopg://clinicflow_owner:clinicflow_owner@localhost:5432/clinicflow"
    )
    # Name of the application role that receives grants in migrations.
    app_db_role: str = "clinicflow_app"

    # OpenID Connect (Keycloak).
    oidc_issuer: str = "http://localhost:8080/realms/clinicflow"
    oidc_audience: str = "clinicflow-api"
    oidc_jwks_url: str | None = None
    # Providers that only allow namespaced custom claims in access tokens (Auth0) put
    # email, email_verified and name under this prefix, e.g. "https://clinicflow.app/".
    oidc_claim_namespace: str = ""
    oidc_algorithms: list[str] = Field(default_factory=lambda: ["RS256"])
    # When non-empty, users holding privileged permissions must present a token
    # whose `acr` claim is one of these values (i.e. they completed MFA).
    oidc_mfa_acr_values: list[str] = Field(default_factory=list)

    # Notification delivery. "log" records that a message would be sent (development);
    # "none" fails delivery so messages stay retryable until a provider is configured.
    # Real SMS/WhatsApp providers are added as adapters once contracts exist.
    sms_provider: Literal["log", "none"] = "log"
    whatsapp_provider: Literal["log", "none"] = "log"
    email_provider: Literal["log", "smtp", "none"] = "log"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = False
    email_from: str = "ClinicFlow <no-reply@clinicflow.local>"
    notification_max_attempts: int = 5
    # Run the notification worker as a thread inside the API process, for hosting that
    # offers a single web service and no background workers (e.g. a free tier).
    run_worker_in_api: bool = False
    # Public URL of the web app, used in patient messages that link to the portal.
    public_web_url: str = "http://localhost:3000"

    # "approval": practices registered by ordinary users start as "pending" until a platform
    # administrator activates them (use on shared hosting). "open": active immediately.
    organisation_signup: Literal["open", "approval"] = "open"

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @field_validator("oidc_issuer", "oidc_jwks_url", "public_web_url", mode="before")
    @classmethod
    def _url(cls, value: object, info) -> object:  # type: ignore[no-untyped-def]
        """Catch copy-paste mistakes at start-up rather than at the first sign-in."""
        if value is None:
            return None
        text = str(value).strip()
        if not text and info.field_name == "oidc_jwks_url":
            return None
        if not text.startswith(("https://", "http://")):
            raise ValueError(
                f"CLINICFLOW_{info.field_name.upper()} must start with https:// (got {text[:40]!r})"
            )
        return text

    @property
    def jwks_url(self) -> str:
        return self.oidc_jwks_url or f"{self.oidc_issuer}/protocol/openid-connect/certs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
