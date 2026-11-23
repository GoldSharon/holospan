from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from httpx import AsyncClient

from holospan_api.domains.identity_access.authorization import Actor, Plane
from holospan_api.domains.identity_access.contracts import (
    LogoutResult,
    PrincipalSummary,
    SessionContext,
)
from holospan_api.domains.identity_access.dependencies import (
    current_tenant_request,
    identity_service,
)
from holospan_api.domains.identity_access.service import AuthenticatedRequest
from holospan_api.main import app


async def test_ec10_oidc_config_reports_disabled_without_secrets(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/identity-access/oidc-config")

    assert response.status_code == 200
    assert response.json()["data"] == {"enabled": False}


async def test_ac2_session_fails_closed_without_cookie(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/identity-access/session")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "IDENTITY_NOT_CONFIGURED"


async def test_reveals_bug_parallel_login_starts_keep_independent_transactions(
    api_client: AsyncClient,
) -> None:
    service = MagicMock()
    service.begin_login = AsyncMock(
        side_effect=[
            ("https://id.example/authorize?state=state-one", "transaction-one"),
            ("https://id.example/authorize?state=state-two", "transaction-two"),
        ]
    )

    def service_override() -> MagicMock:
        return service

    app.dependency_overrides[identity_service] = service_override
    try:
        first = await api_client.get("/api/v1/identity-access/login", follow_redirects=False)
        second = await api_client.get("/api/v1/identity-access/login", follow_redirects=False)
    finally:
        app.dependency_overrides.pop(identity_service, None)

    first_name = first.headers["set-cookie"].split("=", 1)[0]
    second_name = second.headers["set-cookie"].split("=", 1)[0]
    assert first.status_code == second.status_code == 302
    assert first_name != second_name
    assert len(api_client.cookies) == 2


async def test_logout_clears_an_expired_local_session_and_returns_upstream_redirect(
    api_client: AsyncClient,
) -> None:
    service = MagicMock()
    service.logout = AsyncMock(
        return_value=LogoutResult(redirectUri="https://id.example/logout")
    )

    def service_override() -> MagicMock:
        return service

    app.dependency_overrides[identity_service] = service_override
    api_client.cookies.set("holospan_tenant_session", "expired-session")
    api_client.cookies.set("holospan_csrf", "expired-csrf")
    try:
        response = await api_client.delete("/api/v1/identity-access/session")
    finally:
        app.dependency_overrides.pop(identity_service, None)

    assert response.status_code == 200
    assert response.json()["data"] == {"redirectUri": "https://id.example/logout"}
    service.logout.assert_awaited_once_with(
        plane=Plane.TENANT,
        session_token="expired-session",  # noqa: S106
    )
    deleted = response.headers.get_list("set-cookie")
    assert any(
        "holospan_tenant_session=" in value and "Max-Age=0" in value for value in deleted
    )
    assert any("holospan_csrf=" in value and "Max-Age=0" in value for value in deleted)


async def test_platform_logout_has_the_same_idempotent_cookie_cleanup(
    api_client: AsyncClient,
) -> None:
    service = MagicMock()
    service.logout = AsyncMock(return_value=LogoutResult(redirectUri="https://id.example/logout"))
    service.audit_denial = AsyncMock()

    def service_override() -> MagicMock:
        return service

    app.dependency_overrides[identity_service] = service_override
    api_client.cookies.set("holospan_platform_session", "expired-platform-session")
    try:
        response = await api_client.delete(
            "/api/v1/platform/identity-access/session",
            headers={"Host": "platform.localhost"},
        )
    finally:
        app.dependency_overrides.pop(identity_service, None)

    assert response.status_code == 200
    service.logout.assert_awaited_once_with(
        plane=Plane.PLATFORM,
        session_token="expired-platform-session",  # noqa: S106
    )
    assert any(
        "holospan_platform_session=" in value and "Max-Age=0" in value
        for value in response.headers.get_list("set-cookie")
    )


async def test_ac10_capabilities_are_no_longer_anonymous(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/system-catalog/capabilities")

    assert response.status_code in {401, 503}
    assert "capabilities" not in response.text


def test_ac17_openapi_declares_cursor_limits_and_typed_pages() -> None:
    document = app.openapi()
    for path in (
        "/api/v1/identity-access/tenants",
        "/api/v1/platform/identity-access/tenants",
        "/api/v1/identity-access/tenants/{tenantId}/members",
    ):
        operation = document["paths"][path]["get"]
        limit = next(item for item in operation["parameters"] if item["name"] == "limit")
        assert limit["schema"]["default"] == 50
        assert limit["schema"]["maximum"] == 100
        response_schema = operation["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        assert "CursorPage" in response_schema["$ref"]


def test_openapi_exposes_plane_specific_opaque_cookie_security() -> None:
    document = app.openapi()
    schemes = document["components"]["securitySchemes"]

    assert schemes["TenantSessionCookie"] == {
        "type": "apiKey",
        "in": "cookie",
        "name": "holospan_tenant_session",
        "description": "Opaque tenant-plane browser session cookie.",
    }
    assert schemes["PlatformSessionCookie"] == {
        "type": "apiKey",
        "in": "cookie",
        "name": "holospan_platform_session",
        "description": "Opaque platform-administration browser session cookie.",
    }
    assert document["paths"]["/api/v1/identity-access/session"]["get"]["security"] == [
        {"TenantSessionCookie": []}
    ]
    assert document["paths"]["/api/v1/platform/identity-access/session"]["get"][
        "security"
    ] == [{"PlatformSessionCookie": []}]


async def test_ac17_runtime_rejects_page_size_above_one_hundred(
    api_client: AsyncClient,
) -> None:
    principal_id = uuid4()
    authenticated = AuthenticatedRequest(
        actor=Actor(principal_id=principal_id, plane=Plane.TENANT),
        context=SessionContext(
            principal=PrincipalSummary(id=principal_id, status="ACTIVE"),
            memberships=[],
            platformRoles=[],
            platformPermissions=[],
            selectedTenantId=None,
            csrfToken="csrf",
            expiresAt="2026-11-22T01:00:00Z",
        ),
    )

    async def authenticated_override() -> AuthenticatedRequest:
        return authenticated

    def service_override() -> MagicMock:
        return MagicMock()

    app.dependency_overrides[current_tenant_request] = authenticated_override
    app.dependency_overrides[identity_service] = service_override
    try:
        response = await api_client.get("/api/v1/identity-access/tenants?limit=101")
    finally:
        app.dependency_overrides.pop(current_tenant_request, None)
        app.dependency_overrides.pop(identity_service, None)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
