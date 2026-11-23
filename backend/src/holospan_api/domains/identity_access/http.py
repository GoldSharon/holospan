import hashlib
from typing import Annotated
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response
from fastapi.responses import RedirectResponse

from holospan_api.core.config import get_settings
from holospan_api.core.contracts import Envelope, ErrorEnvelope
from holospan_api.core.http import response_meta
from holospan_api.domains.identity_access.authorization import Actor, Plane
from holospan_api.domains.identity_access.contracts import (
    CreateTenantRequest,
    CursorPage,
    LogoutResult,
    MemberSummary,
    OidcClientConfig,
    ReplaceMemberRolesRequest,
    SessionContext,
    TenantSummary,
)
from holospan_api.domains.identity_access.dependencies import (
    CSRF_COOKIE,
    LOGIN_TRANSACTION_COOKIE,
    PLATFORM_SESSION_COOKIE,
    TENANT_SESSION_COOKIE,
    cookie_name,
    current_platform_request,
    current_tenant_request,
    identity_service,
)
from holospan_api.domains.identity_access.errors import permission_denied
from holospan_api.domains.identity_access.service import AuthenticatedRequest, IdentityService

tenant_router = APIRouter(prefix="/api/v1/identity-access", tags=["Identity access"])
platform_router = APIRouter(
    prefix="/api/v1/platform/identity-access",
    tags=["Platform identity access"],
)

AUTH_ERROR = {"model": ErrorEnvelope, "description": "Authentication is required."}
DENIAL_ERROR = {"model": ErrorEnvelope, "description": "Access is not permitted."}
VALIDATION_ERROR = {"model": ErrorEnvelope, "description": "A parameter is invalid."}
DEPENDENCY_ERROR = {"model": ErrorEnvelope, "description": "Identity storage is unavailable."}
CONFLICT_ERROR = {"model": ErrorEnvelope, "description": "The requested state conflicts."}


def _transaction_cookie_name(state: str) -> str:
    state_digest = hashlib.sha256(state.encode()).hexdigest()
    return cookie_name(f"{LOGIN_TRANSACTION_COOKIE}_{state_digest}")


def _authorization_state(location: str) -> str:
    states = parse_qs(urlsplit(location).query).get("state", [])
    if len(states) != 1 or not states[0]:
        raise RuntimeError("OIDC authorization URL is missing its transaction state")
    return states[0]


def _set_transaction_cookie(response: Response, value: str, *, state: str) -> None:
    response.set_cookie(
        _transaction_cookie_name(state),
        value,
        max_age=300,
        secure=get_settings().identity_cookie_secure,
        httponly=True,
        samesite="lax",
        path="/",
    )


def _delete_transaction_cookie(response: Response, name: str) -> None:
    response.delete_cookie(
        name,
        secure=get_settings().identity_cookie_secure,
        httponly=True,
        samesite="lax",
        path="/",
    )


def _clear_transaction_cookie(response: Response, *, state: str) -> None:
    _delete_transaction_cookie(response, _transaction_cookie_name(state))
    _delete_transaction_cookie(response, cookie_name(LOGIN_TRANSACTION_COOKIE))


def _clear_transaction_cookies(response: Response, request: Request) -> None:
    legacy_name = cookie_name(LOGIN_TRANSACTION_COOKIE)
    state_prefix = f"{legacy_name}_"
    for name in request.cookies:
        if name == legacy_name or name.startswith(state_prefix):
            _delete_transaction_cookie(response, name)


def _set_session_cookies(
    response: Response,
    *,
    plane: Plane,
    session_token: str,
    csrf_token: str,
    max_age: int,
) -> None:
    session_name = TENANT_SESSION_COOKIE if plane is Plane.TENANT else PLATFORM_SESSION_COOKIE
    response.set_cookie(
        cookie_name(session_name),
        session_token,
        max_age=max_age,
        secure=get_settings().identity_cookie_secure,
        httponly=True,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        cookie_name(CSRF_COOKIE),
        csrf_token,
        max_age=max_age,
        secure=get_settings().identity_cookie_secure,
        httponly=False,
        samesite="strict",
        path="/",
    )


def _clear_session_cookies(response: Response, plane: Plane) -> None:
    session_name = TENANT_SESSION_COOKIE if plane is Plane.TENANT else PLATFORM_SESSION_COOKIE
    for name in (session_name, CSRF_COOKIE):
        response.delete_cookie(
            cookie_name(name),
            secure=get_settings().identity_cookie_secure,
            httponly=name != CSRF_COOKIE,
            samesite="lax" if name != CSRF_COOKIE else "strict",
            path="/",
        )


async def _require_platform_host(
    request: Request,
    service: IdentityService,
    actor: Actor | None = None,
) -> None:
    if request.url.hostname != get_settings().platform_admin_host:
        await service.audit_denial(
            actor=actor,
            action="platform.host.verify",
            tenant_id=None,
            request_id=request.state.request_id,
        )
        raise permission_denied()


@tenant_router.get(
    "/oidc-config",
    response_model=Envelope[OidcClientConfig],
    response_model_exclude_none=True,
    summary="Read non-secret tenant identity configuration",
    description="Returns tenant OIDC discovery values safe for an unauthenticated browser.",
    openapi_extra={"security": []},
)
async def tenant_oidc_config(
    request: Request,
    service: Annotated[IdentityService, Depends(identity_service)],
) -> Envelope[OidcClientConfig]:
    return Envelope(data=service.public_config(Plane.TENANT), meta=response_meta(request))


@tenant_router.get(
    "/login",
    include_in_schema=True,
    summary="Start tenant OIDC sign-in",
    description="Creates a short-lived PKCE transaction and redirects to the tenant issuer.",
    responses={503: DEPENDENCY_ERROR},
    openapi_extra={"security": []},
)
async def tenant_login(
    service: Annotated[IdentityService, Depends(identity_service)],
) -> RedirectResponse:
    location, transaction = await service.begin_login(Plane.TENANT)
    response = RedirectResponse(location, status_code=302)
    _set_transaction_cookie(response, transaction, state=_authorization_state(location))
    return response


@tenant_router.get(
    "/callback",
    include_in_schema=True,
    summary="Complete tenant OIDC sign-in",
    description="Validates the OIDC callback and issues opaque tenant session cookies.",
    responses={401: AUTH_ERROR, 422: VALIDATION_ERROR, 503: DEPENDENCY_ERROR},
    openapi_extra={"security": []},
)
async def tenant_callback(
    request: Request,
    service: Annotated[IdentityService, Depends(identity_service)],
    code: Annotated[str, Query(min_length=1, max_length=4096)],
    state: Annotated[str, Query(min_length=16, max_length=512)],
) -> RedirectResponse:
    issued = await service.complete_login(
        plane=Plane.TENANT,
        code=code,
        state=state,
        transaction_cookie=(
            request.cookies.get(_transaction_cookie_name(state))
            or request.cookies.get(cookie_name(LOGIN_TRANSACTION_COOKIE))
        ),
        request_id=request.state.request_id,
    )
    response = RedirectResponse(service.configuration(Plane.TENANT).frontend_uri, status_code=302)
    _clear_transaction_cookie(response, state=state)
    _set_session_cookies(
        response,
        plane=Plane.TENANT,
        session_token=issued.session_token,
        csrf_token=issued.csrf_token,
        max_age=get_settings().identity_session_seconds,
    )
    return response


@tenant_router.get(
    "/session",
    response_model=Envelope[SessionContext],
    summary="Read the authenticated tenant session",
    description="Returns tenant-plane identity and membership context for the current cookie.",
    responses={401: AUTH_ERROR, 503: DEPENDENCY_ERROR},
)
async def tenant_session(
    request: Request,
    authenticated: Annotated[AuthenticatedRequest, Depends(current_tenant_request)],
) -> Envelope[SessionContext]:
    return Envelope(data=authenticated.context, meta=response_meta(request))


@tenant_router.get(
    "/tenants",
    response_model=Envelope[CursorPage[TenantSummary]],
    response_model_exclude_none=True,
    summary="List active tenant memberships",
    description=(
        "Returns one stable page of tenants visible to the authenticated tenant session. "
        "Pass nextCursor as cursor to continue."
    ),
    responses={401: AUTH_ERROR, 422: VALIDATION_ERROR, 503: DEPENDENCY_ERROR},
)
async def membership_tenants(
    request: Request,
    authenticated: Annotated[AuthenticatedRequest, Depends(current_tenant_request)],
    service: Annotated[IdentityService, Depends(identity_service)],
    limit: Annotated[int, Query(ge=1, le=100, description="Page size, at most 100.")] = 50,
    cursor: Annotated[
        str | None,
        Query(min_length=1, max_length=2048, description="Opaque continuation cursor."),
    ] = None,
) -> Envelope[CursorPage[TenantSummary]]:
    return Envelope(
        data=await service.list_membership_tenants(
            authenticated, limit=limit, cursor=cursor
        ),
        meta=response_meta(request),
    )


@tenant_router.get(
    "/tenants/{tenantId}/members",
    response_model=Envelope[CursorPage[MemberSummary]],
    response_model_exclude_none=True,
    summary="List tenant members",
    description=(
        "Returns one stable page of members for the selected tenant, with roles and "
        "effective permissions hydrated in one bounded batch query."
    ),
    responses={
        401: AUTH_ERROR,
        403: DENIAL_ERROR,
        422: VALIDATION_ERROR,
        503: DEPENDENCY_ERROR,
    },
)
async def tenant_members(
    request: Request,
    tenant_id: Annotated[
        UUID, Path(alias="tenantId", description="Tenant identifier selected by the session.")
    ],
    authenticated: Annotated[AuthenticatedRequest, Depends(current_tenant_request)],
    service: Annotated[IdentityService, Depends(identity_service)],
    limit: Annotated[int, Query(ge=1, le=100, description="Page size, at most 100.")] = 50,
    cursor: Annotated[
        str | None,
        Query(min_length=1, max_length=2048, description="Opaque continuation cursor."),
    ] = None,
) -> Envelope[CursorPage[MemberSummary]]:
    await service.require_selected_tenant(
        authenticated, tenant_id, request_id=request.state.request_id
    )
    return Envelope(
        data=await service.list_tenant_members(
            authenticated=authenticated,
            tenant_id=tenant_id,
            limit=limit,
            cursor=cursor,
            request_id=request.state.request_id,
        ),
        meta=response_meta(request),
    )


@tenant_router.put(
    "/tenants/{tenantId}/members/{membershipId}/roles",
    response_model=Envelope[MemberSummary],
    summary="Replace a tenant member's roles",
    description=(
        "Atomically replaces a member's tenant roles while preserving at least one active "
        "tenant administrator."
    ),
    responses={
        401: AUTH_ERROR,
        403: DENIAL_ERROR,
        409: CONFLICT_ERROR,
        422: VALIDATION_ERROR,
        503: DEPENDENCY_ERROR,
    },
)
async def replace_tenant_member_roles(
    request: Request,
    tenant_id: Annotated[
        UUID, Path(alias="tenantId", description="Tenant identifier selected by the session.")
    ],
    membership_id: Annotated[
        UUID, Path(alias="membershipId", description="Membership whose roles are replaced.")
    ],
    body: ReplaceMemberRolesRequest,
    authenticated: Annotated[AuthenticatedRequest, Depends(current_tenant_request)],
    service: Annotated[IdentityService, Depends(identity_service)],
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> Envelope[MemberSummary]:
    await service.require_selected_tenant(
        authenticated, tenant_id, request_id=request.state.request_id
    )
    await service.verify_csrf(
        authenticated, csrf_header, request_id=request.state.request_id
    )
    return Envelope(
        data=await service.replace_member_roles(
            authenticated=authenticated,
            tenant_id=tenant_id,
            membership_id=membership_id,
            role_ids=body.role_ids,
            request_id=request.state.request_id,
        ),
        meta=response_meta(request),
    )


@tenant_router.delete(
    "/session",
    response_model=Envelope[LogoutResult],
    summary="Revoke the tenant session",
    description=(
        "Idempotently clears the local browser session and returns the upstream OIDC "
        "end-session destination when the provider publishes one."
    ),
    responses={503: DEPENDENCY_ERROR},
)
async def tenant_logout(
    request: Request,
    response: Response,
    service: Annotated[IdentityService, Depends(identity_service)],
) -> Envelope[LogoutResult]:
    result = await service.logout(
        plane=Plane.TENANT,
        session_token=request.cookies.get(cookie_name(TENANT_SESSION_COOKIE)),
    )
    _clear_session_cookies(response, Plane.TENANT)
    _clear_transaction_cookies(response, request)
    return Envelope(data=result, meta=response_meta(request))


@platform_router.get(
    "/oidc-config",
    response_model=Envelope[OidcClientConfig],
    response_model_exclude_none=True,
    summary="Read non-secret platform identity configuration",
    description="Returns platform OIDC values safe for the isolated administration browser.",
    responses={403: DENIAL_ERROR},
    openapi_extra={"security": []},
)
async def platform_oidc_config(
    request: Request,
    service: Annotated[IdentityService, Depends(identity_service)],
) -> Envelope[OidcClientConfig]:
    await _require_platform_host(request, service)
    return Envelope(data=service.public_config(Plane.PLATFORM), meta=response_meta(request))


@platform_router.get(
    "/login",
    summary="Start platform OIDC sign-in",
    description="Starts PKCE sign-in through the isolated platform administration issuer.",
    responses={403: DENIAL_ERROR, 503: DEPENDENCY_ERROR},
    openapi_extra={"security": []},
)
async def platform_login(
    request: Request,
    service: Annotated[IdentityService, Depends(identity_service)],
) -> RedirectResponse:
    await _require_platform_host(request, service)
    location, transaction = await service.begin_login(Plane.PLATFORM)
    response = RedirectResponse(location, status_code=302)
    _set_transaction_cookie(response, transaction, state=_authorization_state(location))
    return response


@platform_router.get(
    "/callback",
    summary="Complete platform OIDC sign-in",
    description="Validates the platform OIDC callback and issues an opaque platform cookie.",
    responses={
        401: AUTH_ERROR,
        403: DENIAL_ERROR,
        422: VALIDATION_ERROR,
        503: DEPENDENCY_ERROR,
    },
    openapi_extra={"security": []},
)
async def platform_callback(
    request: Request,
    service: Annotated[IdentityService, Depends(identity_service)],
    code: Annotated[str, Query(min_length=1, max_length=4096)],
    state: Annotated[str, Query(min_length=16, max_length=512)],
) -> RedirectResponse:
    await _require_platform_host(request, service)
    issued = await service.complete_login(
        plane=Plane.PLATFORM,
        code=code,
        state=state,
        transaction_cookie=(
            request.cookies.get(_transaction_cookie_name(state))
            or request.cookies.get(cookie_name(LOGIN_TRANSACTION_COOKIE))
        ),
        request_id=request.state.request_id,
    )
    response = RedirectResponse(service.configuration(Plane.PLATFORM).frontend_uri, status_code=302)
    _clear_transaction_cookie(response, state=state)
    _set_session_cookies(
        response,
        plane=Plane.PLATFORM,
        session_token=issued.session_token,
        csrf_token=issued.csrf_token,
        max_age=get_settings().identity_session_seconds,
    )
    return response


@platform_router.get(
    "/session",
    response_model=Envelope[SessionContext],
    summary="Read the authenticated platform session",
    description="Returns platform roles and permissions without tenant membership data.",
    responses={401: AUTH_ERROR, 403: DENIAL_ERROR, 503: DEPENDENCY_ERROR},
)
async def platform_session(
    request: Request,
    authenticated: Annotated[AuthenticatedRequest, Depends(current_platform_request)],
    service: Annotated[IdentityService, Depends(identity_service)],
) -> Envelope[SessionContext]:
    await _require_platform_host(request, service, authenticated.actor)
    return Envelope(data=authenticated.context, meta=response_meta(request))


@platform_router.delete(
    "/session",
    response_model=Envelope[LogoutResult],
    summary="Revoke the platform session",
    description=(
        "Idempotently clears the isolated platform session and returns the upstream OIDC "
        "end-session destination."
    ),
    responses={403: DENIAL_ERROR, 503: DEPENDENCY_ERROR},
)
async def platform_logout(
    request: Request,
    response: Response,
    service: Annotated[IdentityService, Depends(identity_service)],
) -> Envelope[LogoutResult]:
    await _require_platform_host(request, service)
    result = await service.logout(
        plane=Plane.PLATFORM,
        session_token=request.cookies.get(cookie_name(PLATFORM_SESSION_COOKIE)),
    )
    _clear_session_cookies(response, Plane.PLATFORM)
    _clear_transaction_cookies(response, request)
    return Envelope(data=result, meta=response_meta(request))


@platform_router.get(
    "/tenants",
    response_model=Envelope[CursorPage[TenantSummary]],
    response_model_exclude_none=True,
    summary="List platform tenant metadata",
    description=(
        "Returns one stable platform-administration page ordered by tenant creation time "
        "and identifier."
    ),
    responses={
        401: AUTH_ERROR,
        403: DENIAL_ERROR,
        422: VALIDATION_ERROR,
        503: DEPENDENCY_ERROR,
    },
)
async def platform_tenants(
    request: Request,
    authenticated: Annotated[AuthenticatedRequest, Depends(current_platform_request)],
    service: Annotated[IdentityService, Depends(identity_service)],
    limit: Annotated[int, Query(ge=1, le=100, description="Page size, at most 100.")] = 50,
    cursor: Annotated[
        str | None,
        Query(min_length=1, max_length=2048, description="Opaque continuation cursor."),
    ] = None,
) -> Envelope[CursorPage[TenantSummary]]:
    await _require_platform_host(request, service, authenticated.actor)
    return Envelope(
        data=await service.list_platform_tenants(
            authenticated,
            limit=limit,
            cursor=cursor,
            request_id=request.state.request_id,
        ),
        meta=response_meta(request),
    )


@platform_router.post(
    "/tenants",
    response_model=Envelope[TenantSummary],
    status_code=201,
    summary="Create a tenant with its initial administrator",
    description=(
        "Creates tenant metadata and an initial administrator whose verified issuer exactly "
        "matches the configured tenant issuer."
    ),
    responses={
        401: AUTH_ERROR,
        403: DENIAL_ERROR,
        409: CONFLICT_ERROR,
        422: VALIDATION_ERROR,
        503: DEPENDENCY_ERROR,
    },
)
async def create_platform_tenant(
    request: Request,
    body: CreateTenantRequest,
    authenticated: Annotated[AuthenticatedRequest, Depends(current_platform_request)],
    service: Annotated[IdentityService, Depends(identity_service)],
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> Envelope[TenantSummary]:
    await _require_platform_host(request, service, authenticated.actor)
    await service.verify_csrf(
        authenticated, csrf_header, request_id=request.state.request_id
    )
    return Envelope(
        data=await service.create_tenant(
            authenticated=authenticated,
            request=body,
            request_id=request.state.request_id,
        ),
        meta=response_meta(request),
    )
