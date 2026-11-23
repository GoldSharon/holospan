from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from holospan_api.core.config import Settings
from holospan_api.domains.identity_access.authorization import Actor, Plane
from holospan_api.domains.identity_access.contracts import (
    CreateTenantRequest,
    PrincipalSummary,
    SessionContext,
)
from holospan_api.domains.identity_access.errors import IdentityProblem
from holospan_api.domains.identity_access.service import AuthenticatedRequest, IdentityService


def make_service() -> IdentityService:
    auth_session = MagicMock()
    auth_session.commit = AsyncMock()
    auth_session.rollback = AsyncMock()
    tenant_session = MagicMock()
    tenant_session.commit = AsyncMock()
    tenant_session.rollback = AsyncMock()
    service = IdentityService(
        settings=Settings(
            oidc_issuer="https://tenant-id.example",
            identity_session_secret=(  # noqa: S106
                "test-identity-session-secret-at-least-32-bytes"
            ),
        ),
        session=auth_session,
        tenant_session=tenant_session,
        tenant_provider=None,
        platform_provider=None,
    )
    service.repository = MagicMock()
    service.repository.record_authorization_denial = AsyncMock()
    service.tenant_repository = MagicMock()
    service.tenant_repository.activate_tenant_context = AsyncMock()
    return service


def authenticated_request(*, plane: Plane, tenant_id: object | None = None) -> AuthenticatedRequest:
    principal_id = uuid4()
    selected = tenant_id if tenant_id is not None else None
    actor = Actor(
        principal_id=principal_id,
        plane=plane,
        tenant_permissions=(
            {selected: frozenset({"tenant.members.manage"})} if selected else {}
        ),
        platform_permissions=frozenset({"platform.tenants.manage"}),
        session_id=uuid4(),
        session_digest=b"validated-session-digest",
    )
    context = SessionContext(
        principal=PrincipalSummary(id=principal_id, status="ACTIVE"),
        memberships=[],
        platformRoles=[],
        platformPermissions=[],
        selectedTenantId=selected,
        csrfToken="csrf",
        expiresAt=datetime(2026, 11, 22, 1, tzinfo=UTC),
    )
    return AuthenticatedRequest(actor=actor, context=context)


async def test_logout_revokes_an_expired_browser_session_and_ends_oidc_session() -> None:
    service = make_service()
    provider = MagicMock()
    provider.end_session_url = AsyncMock(return_value="https://tenant-id.example/logout")
    service.providers[Plane.TENANT] = provider
    service.repository.revoke_session_token = AsyncMock(return_value=True)

    result = await service.logout(
        plane=Plane.TENANT,
        session_token="expired-session",  # noqa: S106
    )

    service.repository.revoke_session_token.assert_awaited_once()
    service.session.commit.assert_awaited_once()
    assert result.redirect_uri == "https://tenant-id.example/logout"


async def test_logout_still_returns_to_the_frontend_when_revocation_storage_is_down() -> None:
    service = make_service()
    service.repository.revoke_session_token = AsyncMock(
        side_effect=SQLAlchemyError("identity storage unavailable")
    )

    result = await service.logout(
        plane=Plane.TENANT,
        session_token="expired-session",  # noqa: S106
    )

    service.session.rollback.assert_awaited_once()
    assert result.redirect_uri == service.settings.oidc_frontend_uri


async def test_selected_tenant_mismatch_is_audited_before_denial() -> None:
    service = make_service()
    request = authenticated_request(plane=Plane.TENANT, tenant_id=uuid4())
    requested_tenant = uuid4()

    with pytest.raises(IdentityProblem):
        await service.require_selected_tenant(
            request, requested_tenant, request_id="request-1"
        )

    service.repository.record_authorization_denial.assert_awaited_once()


async def test_invalid_role_assignment_is_audited_and_tenant_transaction_rolled_back() -> None:
    service = make_service()
    tenant_id = uuid4()
    request = authenticated_request(plane=Plane.TENANT, tenant_id=tenant_id)
    service.tenant_repository.replace_member_roles = AsyncMock(return_value=None)

    with pytest.raises(IdentityProblem):
        await service.replace_member_roles(
            authenticated=request,
            tenant_id=tenant_id,
            membership_id=uuid4(),
            role_ids=[uuid4()],
            request_id="request-2",
        )

    service.tenant_session.rollback.assert_awaited_once()
    service.repository.record_authorization_denial.assert_awaited_once()


async def test_initial_admin_must_use_exact_configured_tenant_issuer() -> None:
    service = make_service()
    request = authenticated_request(plane=Plane.PLATFORM)
    create = CreateTenantRequest.model_validate(
        {
            "slug": "tenant-one",
            "displayName": "Tenant One",
            "initialAdmin": {
                "issuer": "https://lookalike-tenant-id.example",
                "subject": "admin-1",
            },
        }
    )

    with pytest.raises(IdentityProblem) as error:
        await service.create_tenant(
            authenticated=request, request=create, request_id="request-3"
        )

    assert error.value.code == "INITIAL_ADMIN_ISSUER_INVALID"
    service.repository.record_authorization_denial.assert_awaited_once()
