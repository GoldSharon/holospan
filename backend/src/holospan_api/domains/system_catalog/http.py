from fastapi import APIRouter, Request

from holospan_api.core.config import get_settings
from holospan_api.core.contracts import Envelope
from holospan_api.core.http import response_meta
from holospan_api.domains.system_catalog.catalog import current_capabilities
from holospan_api.domains.system_catalog.contracts import CapabilityCatalog

router = APIRouter(prefix="/api/v1/system-catalog", tags=["System catalog"])


@router.get(
    "/capabilities",
    response_model=Envelope[CapabilityCatalog],
    summary="List implemented platform capabilities",
    description="Returns the capabilities available in this exact backend release.",
)
async def capabilities(request: Request) -> Envelope[CapabilityCatalog]:
    settings = get_settings()
    return Envelope(
        data=CapabilityCatalog(
            service="holospan-api",
            version=settings.version,
            deployment_mode=settings.deployment_mode,
            capabilities=current_capabilities(),
        ),
        meta=response_meta(request),
    )
