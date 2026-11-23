import pytest
from pydantic import ValidationError

from holospan_api.core.config import Settings


def test_production_rejects_insecure_default_session_configuration() -> None:
    with pytest.raises(ValidationError):
        Settings(env="production")


def test_production_accepts_distinct_hosts_https_and_replaced_secret() -> None:
    settings = Settings(
        env="production",
        identity_cookie_secure=True,
        identity_session_secret="this-is-a-replaced-production-session-secret",  # noqa: S106
        database_url="postgresql+asyncpg://auth@db/holospan",
        tenant_database_url="postgresql+asyncpg://tenant@db/holospan",
        oidc_redirect_uri="https://tenant.example/api/v1/identity-access/callback",
        oidc_frontend_uri="https://tenant.example/",
        platform_oidc_redirect_uri=(
            "https://platform.example/api/v1/platform/identity-access/callback"
        ),
        platform_oidc_frontend_uri="https://platform.example/",
        tenant_app_host="tenant.example",
        platform_admin_host="platform.example",
        object_storage_secret_key="this-is-a-replaced-object-storage-secret",  # noqa: S106
        object_storage_secure=True,
    )

    assert settings.identity_cookie_secure


def test_production_enabled_oidc_requires_confidential_client_secrets() -> None:
    with pytest.raises(ValidationError):
        Settings(
            env="production",
            identity_cookie_secure=True,
            identity_session_secret="this-is-a-replaced-production-session-secret",  # noqa: S106
            database_url="postgresql+asyncpg://auth@db/holospan",
            tenant_database_url="postgresql+asyncpg://tenant@db/holospan",
            oidc_enabled=True,
            oidc_issuer="https://tenant-id.example",
            oidc_client_id="tenant-client",
            oidc_redirect_uri="https://tenant.example/api/v1/identity-access/callback",
            oidc_frontend_uri="https://tenant.example/",
            platform_oidc_redirect_uri=(
                "https://platform.example/api/v1/platform/identity-access/callback"
            ),
            platform_oidc_frontend_uri="https://platform.example/",
            tenant_app_host="tenant.example",
            platform_admin_host="platform.example",
        )
