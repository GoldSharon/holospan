from unittest.mock import MagicMock
from uuid import uuid4

from httpx import AsyncClient

from holospan_api.domains.identity_access.authorization import Actor, Plane
from holospan_api.domains.identity_access.contracts import PrincipalSummary, SessionContext
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
