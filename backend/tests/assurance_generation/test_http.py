from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from httpx import AsyncClient
from system_context.test_http import authenticated

from holospan_api.domains.assurance_generation.contracts import (
    ContextSnapshotSummary,
    DiscoveryRunDetail,
)
from holospan_api.domains.assurance_generation.dependencies import assurance_generation_service
from holospan_api.domains.identity_access.dependencies import (
    current_tenant_request,
    identity_service,
)
from holospan_api.main import app


async def test_ac1_start_discovery_requires_csrf_and_returns_safe_context(
    api_client: AsyncClient,
) -> None:
    tenant_id = uuid4()
    system_id = uuid4()
    source_id = uuid4()
    run_id = uuid4()
    snapshot_id = uuid4()
    request_context = authenticated(tenant_id)
    now = datetime.now(UTC)
    service = MagicMock()
    service.start_discovery = AsyncMock(
        return_value=DiscoveryRunDetail(
            id=run_id,
            system_id=system_id,
            status="context_review",
            current_stage="review_context",
            source_ids=[source_id],
            context_snapshot=ContextSnapshotSummary(
                id=snapshot_id,
                system_id=system_id,
                version=1,
                row_version=1,
                status="draft",
                sha256="a" * 64,
                critic_score=1.0,
                content={"components": [], "claims": [], "gaps": []},
                approved_by=None,
                approved_at=None,
                created_at=now,
            ),
            created_at=now,
            updated_at=now,
        )
    )
    identities = MagicMock()
    identities.verify_csrf = AsyncMock()

    async def authenticated_override():
        return request_context

    app.dependency_overrides[current_tenant_request] = authenticated_override
    app.dependency_overrides[identity_service] = lambda: identities
    app.dependency_overrides[assurance_generation_service] = lambda: service
    try:
        response = await api_client.post(
            f"/api/v1/systems/{system_id}/assurance-generation/runs",
            headers={
                "X-Holospan-Tenant-ID": str(tenant_id),
                "X-CSRF-Token": "csrf-value",
                "Idempotency-Key": "discovery-http-v1",
            },
            json={"sourceIds": [str(source_id)], "budgetProfile": "balanced"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["data"]["status"] == "context_review"
    assert "objectKey" not in str(response.json())
    identities.verify_csrf.assert_awaited_once()
