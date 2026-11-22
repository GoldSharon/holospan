from functools import lru_cache
from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="HOLOSPAN_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Holospan API"
    version: str = "0.1.0"
    env: str = "development"
    deployment_mode: str = "docker-compose"
    database_url: str = "postgresql+asyncpg://holospan@localhost:5432/holospan"
    tenant_database_url: str = "postgresql+asyncpg://holospan@localhost:5432/holospan"
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    docs_enabled: bool = True
    max_request_bytes: int = Field(default=2 * 1024 * 1024, ge=1024, le=10 * 1024 * 1024)
    oidc_enabled: bool = False
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: SecretStr | None = None
    oidc_redirect_uri: str = "http://localhost:8080/api/v1/identity-access/callback"
    oidc_frontend_uri: str = "http://localhost:8080/"
    oidc_scope: str = "openid profile email"
    oidc_algorithms: str = "RS256,ES256"
    oidc_metadata_cache_seconds: int = Field(default=300, ge=30, le=3600)
    identity_session_secret: SecretStr = SecretStr(
        "development-only-replace-with-at-least-32-random-bytes"
    )
    identity_session_seconds: int = Field(default=3600, ge=300, le=43200)
    identity_cookie_secure: bool = False
    bootstrap_platform_admins: str = ""
    tenant_app_host: str = "localhost"
    platform_admin_host: str = "platform.localhost"
    platform_oidc_enabled: bool = False
    platform_oidc_issuer: str | None = None
    platform_oidc_client_id: str | None = None
    platform_oidc_client_secret: SecretStr | None = None
    platform_oidc_redirect_uri: str = (
        "http://platform.localhost:8080/api/v1/platform/identity-access/callback"
    )
    platform_oidc_frontend_uri: str = "http://platform.localhost:8080/"

    @model_validator(mode="after")
    def validate_identity_security(self) -> Self:
        if self.oidc_enabled and not (self.oidc_issuer and self.oidc_client_id):
            raise ValueError("tenant OIDC requires issuer and client ID")
        if self.platform_oidc_enabled and not (
            self.platform_oidc_issuer and self.platform_oidc_client_id
        ):
            raise ValueError("platform OIDC requires issuer and client ID")
        if self.env == "production":
            if not self.identity_cookie_secure:
                raise ValueError("production identity cookies must be secure")
            if self.identity_session_secret.get_secret_value().startswith("development-only"):
                raise ValueError("production identity session secret must be replaced")
            if len(self.identity_session_secret.get_secret_value().encode()) < 32:
                raise ValueError("production identity session secret must be at least 32 bytes")
            if self.database_url == self.tenant_database_url:
                raise ValueError("production auth and tenant database pools must be distinct")
            if self.tenant_app_host == self.platform_admin_host:
                raise ValueError("tenant and platform administration hosts must be distinct")
            if self.oidc_enabled and (
                self.oidc_client_secret is None
                or not self.oidc_client_secret.get_secret_value()
            ):
                raise ValueError("production tenant OIDC requires a client secret")
            if self.platform_oidc_enabled and (
                self.platform_oidc_client_secret is None
                or not self.platform_oidc_client_secret.get_secret_value()
            ):
                raise ValueError("production platform OIDC requires a client secret")
            urls = [
                self.oidc_issuer,
                self.oidc_redirect_uri,
                self.oidc_frontend_uri,
                self.platform_oidc_issuer,
                self.platform_oidc_redirect_uri,
                self.platform_oidc_frontend_uri,
            ]
            if any(value and not value.startswith("https://") for value in urls):
                raise ValueError("production identity endpoints must use HTTPS")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def oidc_algorithm_list(self) -> list[str]:
        return [value.strip() for value in self.oidc_algorithms.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
