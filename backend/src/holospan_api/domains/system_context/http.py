from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status

from holospan_api.core.contracts import Envelope
from holospan_api.core.http import response_meta
from holospan_api.domains.identity_access.dependencies import (
    current_tenant_request,
    identity_service,
)
from holospan_api.domains.identity_access.service import AuthenticatedRequest, IdentityService
from holospan_api.domains.system_context.contracts import (
    CreateSystemRequest,
    SystemList,
    SystemSummary,
)
from holospan_api.domains.system_context.dependencies import system_context_service
from holospan_api.domains.system_context.service import SystemContextService

router = APIRouter(prefix="/api/v1/system-context", tags=["system-context"])


@router.get(
    "/systems",
    response_model=Envelope[SystemList],
    summary="List systems in the selected workspace",
    description="Lists only system metadata visible in the selected tenant context.",
    responses={401: {"description": "Authentication required"}, 403: {"description": "Denied"}},
)
async def list_systems(
    request: Request,
    tenant_id: Annotated[UUID, Header(alias="X-Holospan-Tenant-ID")],
    authenticated: Annotated[AuthenticatedRequest, Depends(current_tenant_request)],
    service: Annotated[SystemContextService, Depends(system_context_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Envelope[SystemList]:
    return Envelope(
        data=await service.list_systems(
            authenticated=authenticated,
            tenant_id=tenant_id,
            limit=limit,
            request_id=request.state.request_id,
        ),
        meta=response_meta(request),
    )


@router.post(
    "/systems",
    response_model=Envelope[SystemSummary],
    status_code=status.HTTP_201_CREATED,
    summary="Create a system in the selected workspace",
    description="Creates tenant-isolated system metadata and an authorization audit event.",
    responses={
        401: {"description": "Authentication required"},
        403: {"description": "Denied"},
        409: {"description": "Slug conflict"},
        422: {"description": "Validation error"},
    },
)
async def create_system(
    request: Request,
    body: CreateSystemRequest,
    tenant_id: Annotated[UUID, Header(alias="X-Holospan-Tenant-ID")],
    authenticated: Annotated[AuthenticatedRequest, Depends(current_tenant_request)],
    identities: Annotated[IdentityService, Depends(identity_service)],
    service: Annotated[SystemContextService, Depends(system_context_service)],
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> Envelope[SystemSummary]:
    await identities.verify_csrf(
        authenticated,
        csrf_header,
        request_id=request.state.request_id,
    )
    return Envelope(
        data=await service.create_system(
            authenticated=authenticated,
            tenant_id=tenant_id,
            request=body,
            request_id=request.state.request_id,
        ),
        meta=response_meta(request),
    )
