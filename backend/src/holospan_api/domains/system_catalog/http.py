from typing import Annotated

from fastapi import APIRouter, Depends, Request

from holospan_api.core.config import get_settings
from holospan_api.core.contracts import Envelope, ErrorEnvelope
from holospan_api.core.http import response_meta
from holospan_api.domains.identity_access.authorization import Actor
from holospan_api.domains.identity_access.dependencies import current_tenant_actor
from holospan_api.domains.system_catalog.catalog import current_capabilities
from holospan_api.domains.system_catalog.contracts import CapabilityCatalog

router = APIRouter(prefix="/api/v1/system-catalog", tags=["System catalog"])


@router.get(
    "/capabilities",
    response_model=Envelope[CapabilityCatalog],
    summary="List implemented platform capabilities",
    description="Returns the capabilities available in this exact backend release.",
    responses={
        401: {"model": ErrorEnvelope, "description": "Authentication is required."},
        503: {"model": ErrorEnvelope, "description": "Identity is not configured."},
    },
)
async def capabilities(
    request: Request,
    _actor: Annotated[Actor, Depends(current_tenant_actor)],
) -> Envelope[CapabilityCatalog]:
    settings = get_settings()
    return Envelope(
        data=CapabilityCatalog.model_validate(
            {
                "service": "holospan-api",
                "version": settings.version,
                "deploymentMode": settings.deployment_mode,
                "capabilities": current_capabilities(),
            }
        ),
        meta=response_meta(request),
    )
