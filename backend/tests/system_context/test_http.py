from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from httpx import AsyncClient

from holospan_api.domains.identity_access.authorization import Actor, Plane
from holospan_api.domains.identity_access.contracts import PrincipalSummary, SessionContext
from holospan_api.domains.identity_access.dependencies import (
    current_tenant_request,
    identity_service,
)
from holospan_api.domains.identity_access.service import AuthenticatedRequest
from holospan_api.domains.system_context.contracts import SystemSummary
from holospan_api.domains.system_context.dependencies import system_context_service
from holospan_api.main import app


def authenticated(tenant_id: object) -> AuthenticatedRequest:
    principal_id = uuid4()
    return AuthenticatedRequest(
        actor=Actor(
            principal_id=principal_id,
            plane=Plane.TENANT,
            tenant_permissions={
                tenant_id: frozenset(
                    {"system_context.systems.read", "system_context.systems.manage"}
                )
            },
            session_id=uuid4(),
        ),
        context=SessionContext(
            principal=PrincipalSummary(id=principal_id, status="ACTIVE"),
            memberships=[],
            platformRoles=[],
            platformPermissions=[],
            selectedTenantId=tenant_id,
            csrfToken="csrf",
            expiresAt="2026-11-22T01:00:00Z",
        ),
    )


async def test_ac3_post_returns_201_and_verifies_csrf(api_client: AsyncClient) -> None:
    tenant_id = uuid4()
    request_context = authenticated(tenant_id)
    now = datetime.now(UTC)
    summary = SystemSummary.model_validate(
        {
            "id": uuid4(),
            "tenantId": tenant_id,
            "displayName": "Claims Copilot",
            "slug": "claims-copilot",
            "description": None,
            "systemType": "agent",
            "lifecycleStage": "development",
            "status": "draft",
            "createdBy": request_context.actor.principal_id,
            "createdAt": now,
            "updatedAt": now,
        }
    )
    system_service = MagicMock()
    system_service.create_system = AsyncMock(return_value=summary)
    identities = MagicMock()
    identities.verify_csrf = AsyncMock()

    async def authenticated_override() -> AuthenticatedRequest:
        return request_context

    def identity_override() -> MagicMock:
        return identities

    def system_override() -> MagicMock:
        return system_service

    app.dependency_overrides[current_tenant_request] = authenticated_override
    app.dependency_overrides[identity_service] = identity_override
    app.dependency_overrides[system_context_service] = system_override
    try:
        response = await api_client.post(
            "/api/v1/system-context/systems",
            headers={
                "X-Holospan-Tenant-ID": str(tenant_id),
                "X-CSRF-Token": "csrf-value",
            },
            json={
                "displayName": "Claims Copilot",
                "slug": "claims-copilot",
                "systemType": "agent",
                "lifecycleStage": "development",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["data"]["slug"] == "claims-copilot"
    identities.verify_csrf.assert_awaited_once()


async def test_ac9_list_limit_is_capped_at_one_hundred(api_client: AsyncClient) -> None:
    tenant_id = uuid4()
    request_context = authenticated(tenant_id)

    async def authenticated_override() -> AuthenticatedRequest:
        return request_context

    app.dependency_overrides[current_tenant_request] = authenticated_override
    try:
        response = await api_client.get(
            "/api/v1/system-context/systems?limit=101",
            headers={"X-Holospan-Tenant-ID": str(tenant_id)},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
