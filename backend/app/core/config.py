from functools import lru_cache
from typing import Literal

from pydantic import Field
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
    oidc_algorithms: list[str] = Field(default_factory=lambda: ["RS256"])
    # When non-empty, users holding privileged permissions must present a token
    # whose `acr` claim is one of these values (i.e. they completed MFA).
    oidc_mfa_acr_values: list[str] = Field(default_factory=list)

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @property
    def jwks_url(self) -> str:
        return self.oidc_jwks_url or f"{self.oidc_issuer}/protocol/openid-connect/certs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
