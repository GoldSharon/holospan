from uuid import uuid4

from httpx import AsyncClient

from holospan_api.domains.identity_access.authorization import Actor, Plane
from holospan_api.domains.identity_access.dependencies import current_tenant_actor
from holospan_api.main import app


async def test_catalog_reports_implemented_and_planned_states(api_client: AsyncClient) -> None:
    async def authenticated_actor() -> Actor:
        return Actor(principal_id=uuid4(), plane=Plane.TENANT)

    app.dependency_overrides[current_tenant_actor] = authenticated_actor
    try:
        response = await api_client.get("/api/v1/system-catalog/capabilities")
    finally:
        app.dependency_overrides.pop(current_tenant_actor, None)

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["deploymentMode"] == "docker-compose"
    assert {item["status"] for item in body["data"]["capabilities"]} == {
        "available",
        "planned",
    }
