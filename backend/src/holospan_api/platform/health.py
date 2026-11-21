from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from holospan_api.core.config import get_settings
from holospan_api.core.contracts import Envelope
from holospan_api.core.database import engine
from holospan_api.core.http import response_meta

router = APIRouter(prefix="/api/v1/health", tags=["Health"])
DatabaseStatus = Literal["ok", "unavailable"]


class HealthData(BaseModel):
    service: str
    version: str
    status: Literal["ok", "degraded"]
    checks: dict[str, DatabaseStatus] = Field(default_factory=dict)


@router.get(
    "/liveness",
    response_model=Envelope[HealthData],
    summary="Check API process liveness",
    description=(
        "Returns success when the API process can serve requests. It does not test dependencies."
    ),
)
async def liveness(request: Request) -> Envelope[HealthData]:
    settings = get_settings()
    return Envelope(
        data=HealthData(service="holospan-api", version=settings.version, status="ok"),
        meta=response_meta(request),
    )


@router.get(
    "/readiness",
    response_model=Envelope[HealthData],
    responses={503: {"description": "A required dependency is unavailable"}},
    summary="Check API readiness",
    description="Checks the authoritative PostgreSQL dependency before declaring the API ready.",
)
async def readiness(request: Request, response: Response) -> Envelope[HealthData]:
    settings = get_settings()
    database_status: DatabaseStatus = "ok"

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        database_status = "unavailable"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return Envelope(
        data=HealthData(
            service="holospan-api",
            version=settings.version,
            status="ok" if database_status == "ok" else "degraded",
            checks={"postgresql": database_status},
        ),
        meta=response_meta(request),
    )
