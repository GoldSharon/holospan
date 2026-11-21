from httpx import AsyncClient


async def test_liveness_contract(api_client: AsyncClient) -> None:
    response = await api_client.get(
        "/api/v1/health/liveness",
        headers={"X-Request-ID": "test-id"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-id"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.json()["data"] == {
        "service": "holospan-api",
        "version": "0.1.0",
        "status": "ok",
        "checks": {},
    }
    assert response.json()["meta"]["requestId"] == "test-id"


async def test_unknown_route_does_not_leak_stack_trace(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/not-a-resource")

    assert response.status_code == 404
    assert "traceback" not in response.text.lower()
