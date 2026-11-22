from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from holospan_api.domains.identity_access.authorization import Actor, Plane
from holospan_api.domains.identity_access.contracts import PrincipalSummary, SessionContext
from holospan_api.domains.identity_access.errors import IdentityProblem
from holospan_api.domains.identity_access.service import AuthenticatedRequest
from holospan_api.domains.system_context.contracts import CreateSystemRequest
from holospan_api.domains.system_context.models import SystemRecord
from holospan_api.domains.system_context.service import SystemContextService


def authenticated_request(tenant_id: object) -> AuthenticatedRequest:
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
            session_digest=b"validated-session-digest",
        ),
        context=SessionContext(
            principal=PrincipalSummary(id=principal_id, status="ACTIVE"),
            memberships=[],
            platformRoles=[],
            platformPermissions=[],
            selectedTenantId=tenant_id,
            csrfToken="csrf",
        ),
    )


def make_service() -> tuple[SystemContextService, MagicMock, MagicMock]:
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    identity = MagicMock()
    identity.authorize_tenant = AsyncMock()
    service = SystemContextService(session=session, identity_service=identity)
    service.repository = MagicMock()
    return service, session, identity


def create_request() -> CreateSystemRequest:
    return CreateSystemRequest.model_validate(
        {
            "displayName": "Claims Copilot",
            "slug": "claims-copilot",
            "description": "Assists claims reviewers.",
            "systemType": "agent",
            "lifecycleStage": "development",
        }
    )


async def test_ac3_create_is_authorized_audited_and_committed_atomically() -> None:
    service, session, identity = make_service()
    tenant_id = uuid4()
    authenticated = authenticated_request(tenant_id)
    now = datetime.now(UTC)
    record = SystemRecord(
        id=uuid4(),
        tenant_id=tenant_id,
        display_name="Claims Copilot",
        slug="claims-copilot",
        description="Assists claims reviewers.",
        system_type="agent",
        lifecycle_stage="development",
        status="draft",
        created_by=authenticated.actor.principal_id,
        created_at=now,
        updated_at=now,
    )
    service.repository.create_system = AsyncMock(return_value=record)

    result = await service.create_system(
        authenticated=authenticated,
        tenant_id=tenant_id,
        request=create_request(),
        request_id="request-1",
    )

    identity.authorize_tenant.assert_awaited_once_with(
        authenticated,
        tenant_id,
        permission="system_context.systems.manage",
        request_id="request-1",
    )
    service.repository.create_system.assert_awaited_once()
    session.commit.assert_awaited_once()
    assert result.slug == "claims-copilot"


async def test_ec5_duplicate_slug_rolls_back_and_returns_conflict() -> None:
    service, session, _identity = make_service()
    tenant_id = uuid4()
    service.repository.create_system = AsyncMock(
        side_effect=IntegrityError("insert", {}, Exception("unique"))
    )

    with pytest.raises(IdentityProblem) as problem:
        await service.create_system(
            authenticated=authenticated_request(tenant_id),
            tenant_id=tenant_id,
            request=create_request(),
            request_id="request-2",
        )

    assert problem.value.code == "SYSTEM_SLUG_CONFLICT"
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


async def test_ec6_database_failure_rolls_back_without_disclosing_details() -> None:
    service, session, _identity = make_service()
    tenant_id = uuid4()
    service.repository.create_system = AsyncMock(
        side_effect=SQLAlchemyError("credential=should-not-leak")
    )

    with pytest.raises(IdentityProblem) as problem:
        await service.create_system(
            authenticated=authenticated_request(tenant_id),
            tenant_id=tenant_id,
            request=create_request(),
            request_id="request-3",
        )

    assert problem.value.code == "SYSTEM_CONTEXT_UNAVAILABLE"
    assert "credential" not in problem.value.message
    session.rollback.assert_awaited_once()
