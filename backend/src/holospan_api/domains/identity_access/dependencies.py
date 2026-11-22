from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyCookie
from sqlalchemy.ext.asyncio import AsyncSession

from holospan_api.core.config import Settings, get_settings
from holospan_api.core.database import database_session, tenant_database_session
from holospan_api.domains.identity_access.authorization import Actor, Plane
from holospan_api.domains.identity_access.oidc import OidcProvider
from holospan_api.domains.identity_access.service import AuthenticatedRequest, IdentityService

TENANT_SESSION_COOKIE = "holospan_tenant_session"
PLATFORM_SESSION_COOKIE = "holospan_platform_session"
LOGIN_TRANSACTION_COOKIE = "holospan_oidc_transaction"
CSRF_COOKIE = "holospan_csrf"


def cookie_name(name: str) -> str:
    return f"__Host-{name}" if get_settings().identity_cookie_secure else name


tenant_session_scheme = APIKeyCookie(
    name=cookie_name(TENANT_SESSION_COOKIE),
    scheme_name="TenantSessionCookie",
    description="Opaque tenant-plane browser session cookie.",
    auto_error=False,
)
platform_session_scheme = APIKeyCookie(
    name=cookie_name(PLATFORM_SESSION_COOKIE),
    scheme_name="PlatformSessionCookie",
    description="Opaque platform-administration browser session cookie.",
    auto_error=False,
)


def _provider(
    *,
    enabled: bool,
    issuer: str | None,
    client_id: str | None,
    client_secret: str | None,
    settings: Settings,
) -> OidcProvider | None:
    if not enabled or issuer is None or client_id is None:
        return None
    return OidcProvider(
        issuer=issuer,
        client_id=client_id,
        client_secret=client_secret,
        algorithms=settings.oidc_algorithm_list,
        cache_seconds=settings.oidc_metadata_cache_seconds,
        allow_insecure_http=settings.env == "development",
    )


@lru_cache
def tenant_provider() -> OidcProvider | None:
    settings = get_settings()
    return _provider(
        enabled=settings.oidc_enabled,
        issuer=settings.oidc_issuer,
        client_id=settings.oidc_client_id,
        client_secret=(
            settings.oidc_client_secret.get_secret_value()
            if settings.oidc_client_secret is not None
            else None
        ),
        settings=settings,
    )


@lru_cache
def platform_provider() -> OidcProvider | None:
    settings = get_settings()
    return _provider(
        enabled=settings.platform_oidc_enabled,
        issuer=settings.platform_oidc_issuer,
        client_id=settings.platform_oidc_client_id,
        client_secret=(
            settings.platform_oidc_client_secret.get_secret_value()
            if settings.platform_oidc_client_secret is not None
            else None
        ),
        settings=settings,
    )


async def identity_service(
    session: Annotated[AsyncSession, Depends(database_session)],
    tenant_session: Annotated[AsyncSession, Depends(tenant_database_session)],
) -> IdentityService:
    return IdentityService(
        settings=get_settings(),
        session=session,
        tenant_session=tenant_session,
        tenant_provider=tenant_provider(),
        platform_provider=platform_provider(),
    )


async def current_tenant_request(
    request: Request,
    service: Annotated[IdentityService, Depends(identity_service)],
    session_token: Annotated[str | None, Security(tenant_session_scheme)],
) -> AuthenticatedRequest:
    tenant_value = request.headers.get("X-Holospan-Tenant-ID")
    try:
        tenant_id = UUID(tenant_value) if tenant_value else None
    except ValueError:
        tenant_id = None
    return await service.authenticate(
        plane=Plane.TENANT,
        session_token=session_token,
        csrf_token=request.cookies.get(cookie_name(CSRF_COOKIE)),
        selected_tenant_id=tenant_id,
        request_id=request.state.request_id,
    )


async def current_tenant_actor(
    request: Annotated[AuthenticatedRequest, Depends(current_tenant_request)],
) -> Actor:
    return request.actor


async def current_platform_request(
    request: Request,
    service: Annotated[IdentityService, Depends(identity_service)],
    session_token: Annotated[str | None, Security(platform_session_scheme)],
) -> AuthenticatedRequest:
    return await service.authenticate(
        plane=Plane.PLATFORM,
        session_token=session_token,
        csrf_token=request.cookies.get(cookie_name(CSRF_COOKIE)),
        selected_tenant_id=None,
        request_id=request.state.request_id,
    )
