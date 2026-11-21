from httpx import AsyncClient


async def test_catalog_reports_implemented_and_planned_states(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/system-catalog/capabilities")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["deploymentMode"] == "docker-compose"
    assert {item["status"] for item in body["data"]["capabilities"]} == {
        "available",
        "planned",
    }
