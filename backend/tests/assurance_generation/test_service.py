import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from system_context.test_service import authenticated_request

from holospan_api.domains.assurance_generation.contracts import (
    ReviewContextRequest,
    StartDiscoveryRequest,
)
from holospan_api.domains.assurance_generation.service import AssuranceGenerationService
from holospan_api.domains.identity_access.errors import IdentityProblem
from holospan_api.domains.system_context.models import SourceKind


def make_service() -> tuple[AssuranceGenerationService, MagicMock, MagicMock, MagicMock]:
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    identity = MagicMock()
    identity.authorize_tenant = AsyncMock()
    storage = MagicMock()
    storage.get_object = AsyncMock()
    storage.put_object = AsyncMock()
    storage.delete_object = AsyncMock()
    service = AssuranceGenerationService(
        session=session,
        identity_service=identity,
        object_storage=storage,
        context_bucket="holospan-evidence",
    )
    service.repository = MagicMock()
    service.repository.get_existing_run = AsyncMock(return_value=None)
    return service, session, identity, storage


async def test_ac1_document_only_discovery_persists_reviewable_context() -> None:
    service, session, identity, storage = make_service()
    tenant_id = uuid4()
    system_id = uuid4()
    source_id = uuid4()
    principal = authenticated_request(tenant_id)
    now = datetime.now(UTC)
    service.repository.get_system = AsyncMock(
        return_value=SimpleNamespace(id=system_id, display_name="Travel Agent")
    )
    source_content = (
        b"Agent: Trip Planner\n"
        b"Purpose: Help customers plan travel.\n"
        b"Capability: Search hotels by destination and budget.\n"
    )
    service.repository.get_sources = AsyncMock(
        return_value=[
            SimpleNamespace(
                id=source_id,
                system_id=system_id,
                kind=SourceKind.CONTEXT_DOCUMENT,
                original_filename="travel-prd.md",
                sha256=hashlib.sha256(source_content).hexdigest(),
                storage_bucket="holospan-raw",
                object_key=f"tenants/{tenant_id}/systems/{system_id}/sources/{source_id}/raw",
            )
        ]
    )
    storage.get_object.return_value = source_content

    async def persist(**values: object):
        result = values["result"]
        run_id = values["run_id"]
        snapshot_id = values["snapshot_id"]
        return (
            SimpleNamespace(
                id=run_id,
                system_id=system_id,
                status="context_review",
                current_stage="review_context",
                source_manifest=[str(source_id)],
                context_snapshot_id=snapshot_id,
                created_at=now,
                updated_at=now,
            ),
            SimpleNamespace(
                id=snapshot_id,
                system_id=system_id,
                version=1,
                row_version=1,
                status="draft",
                sha256=result.snapshot.content_sha256,
                content=result.snapshot.model_dump(mode="json"),
                critic_score=result.critic.score,
                critic=result.critic.model_dump(mode="json"),
                approved_by=None,
                approved_at=None,
                created_at=now,
            ),
        )

    service.repository.persist_discovery_result = AsyncMock(side_effect=persist)

    response = await service.start_discovery(
        authenticated=principal,
        tenant_id=tenant_id,
        system_id=system_id,
        request=StartDiscoveryRequest(source_ids=[source_id], budget_profile="balanced"),
        idempotency_key="discovery-travel-v1",
        request_id="request-assurance-1",
    )

    identity.authorize_tenant.assert_awaited_once_with(
        principal,
        tenant_id,
        permission="assurance_generation.context.generate",
        request_id="request-assurance-1",
    )
    storage.get_object.assert_awaited_once()
    assert storage.put_object.await_args.kwargs["bucket"] == "holospan-evidence"
    assert storage.put_object.await_args.kwargs["object_key"].endswith("/context.json")
    assert response.status == "context_review"
    assert response.context_snapshot is not None
    assert response.context_snapshot.critic_score >= 0.9
    assert response.context_snapshot.content["components"][0]["display_name"] == "Trip Planner"
    assert "objectKey" not in response.context_snapshot.model_dump(by_alias=True)
    session.commit.assert_awaited_once()


async def test_ac5_context_cannot_be_approved_when_critic_failed() -> None:
    service, session, _identity, _storage = make_service()
    tenant_id = uuid4()
    snapshot_id = uuid4()
    service.repository.get_snapshot = AsyncMock(
        return_value=SimpleNamespace(
            id=snapshot_id,
            tenant_id=tenant_id,
            system_id=uuid4(),
            row_version=1,
            status="draft",
            critic_score=0.75,
            critic={"passed": False},
        )
    )

    with pytest.raises(IdentityProblem) as problem:
        await service.review_context(
            authenticated=authenticated_request(tenant_id),
            tenant_id=tenant_id,
            snapshot_id=snapshot_id,
            request=ReviewContextRequest(
                decision="approve",
                comment="Looks good",
                expected_version=1,
            ),
            request_id="request-assurance-review-fail",
        )

    assert problem.value.code == "CONTEXT_QUALITY_GATE_FAILED"
    service.repository.review_snapshot.assert_not_called()
    session.commit.assert_not_awaited()


async def test_ac5_approved_context_uses_optimistic_version_and_actor() -> None:
    service, session, identity, _storage = make_service()
    tenant_id = uuid4()
    snapshot_id = uuid4()
    principal = authenticated_request(tenant_id)
    now = datetime.now(UTC)
    snapshot = SimpleNamespace(
        id=snapshot_id,
        tenant_id=tenant_id,
        system_id=uuid4(),
        version=1,
        row_version=1,
        status="draft",
        sha256="b" * 64,
        content={"claims": [], "components": [], "gaps": []},
        critic_score=1.0,
        critic={"passed": True, "score": 1.0, "gates": {}, "issues": []},
        approved_by=None,
        approved_at=None,
        created_at=now,
    )
    service.repository.get_snapshot = AsyncMock(return_value=snapshot)

    async def approve(**values: object):
        snapshot.status = values["decision"] + "d"
        snapshot.row_version = 2
        snapshot.approved_by = values["actor"].principal_id
        snapshot.approved_at = now
        return snapshot

    service.repository.review_snapshot = AsyncMock(side_effect=approve)

    result = await service.review_context(
        authenticated=principal,
        tenant_id=tenant_id,
        snapshot_id=snapshot_id,
        request=ReviewContextRequest(
            decision="approve",
            comment="Approved for scenario planning",
            expected_version=1,
        ),
        request_id="request-assurance-review-pass",
    )

    identity.authorize_tenant.assert_awaited_once_with(
        principal,
        tenant_id,
        permission="assurance_generation.context.review",
        request_id="request-assurance-review-pass",
    )
    assert result.status == "approved"
    assert result.row_version == 2
    session.commit.assert_awaited_once()
