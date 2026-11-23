from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from httpx import AsyncClient

from holospan_api.domains.identity_access.dependencies import (
    current_tenant_request,
    identity_service,
)
from holospan_api.domains.system_context.contracts import SourceSummary
from holospan_api.domains.system_context.dependencies import system_context_service
from holospan_api.main import app

from .test_http import authenticated


async def test_ac3_upload_contract_is_multipart_and_verifies_csrf(
    api_client: AsyncClient,
) -> None:
    tenant_id = uuid4()
    system_id = uuid4()
    request_context = authenticated(tenant_id)
    now = datetime.now(UTC)
    summary = SourceSummary.model_validate(
        {
            "id": uuid4(),
            "systemId": system_id,
            "kind": "api_contract",
            "originalFilename": "openapi.yaml",
            "declaredMediaType": "application/yaml",
            "detectedMediaType": "application/yaml",
            "byteSize": 14,
            "sha256": "a" * 64,
            "status": "stored",
            "createdBy": request_context.actor.principal_id,
            "createdAt": now,
        }
    )
    source_service = MagicMock()
    source_service.create_source = AsyncMock(return_value=summary)
    identities = MagicMock()
    identities.verify_csrf = AsyncMock()

    async def authenticated_override():
        return request_context

    app.dependency_overrides[current_tenant_request] = authenticated_override
    app.dependency_overrides[identity_service] = lambda: identities
    app.dependency_overrides[system_context_service] = lambda: source_service
    try:
        response = await api_client.post(
            f"/api/v1/system-context/systems/{system_id}/sources",
            headers={
                "X-Holospan-Tenant-ID": str(tenant_id),
                "X-CSRF-Token": "csrf-value",
            },
            data={"kind": "api_contract"},
            files={"file": ("openapi.yaml", b"openapi: 3.1\n", "application/yaml")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["data"]["kind"] == "api_contract"
    assert "objectKey" not in response.json()["data"]
    identities.verify_csrf.assert_awaited_once()
    assert source_service.create_source.await_args.kwargs["content"] == b"openapi: 3.1\n"
