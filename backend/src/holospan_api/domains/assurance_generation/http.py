from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status

from holospan_api.core.contracts import Envelope
from holospan_api.core.http import response_meta
from holospan_api.domains.assurance_generation.contracts import (
    ContextSnapshotList,
    ContextSnapshotSummary,
    DiscoveryRunDetail,
    ReviewContextRequest,
    StartDiscoveryRequest,
)
from holospan_api.domains.assurance_generation.dependencies import assurance_generation_service
from holospan_api.domains.assurance_generation.service import AssuranceGenerationService
from holospan_api.domains.identity_access.dependencies import (
    current_tenant_request,
    identity_service,
)
from holospan_api.domains.identity_access.service import AuthenticatedRequest, IdentityService

router = APIRouter(prefix="/api/v1", tags=["assurance-generation"])


@router.post(
    "/systems/{system_id}/assurance-generation/runs",
    response_model=Envelope[DiscoveryRunDetail],
    status_code=status.HTTP_201_CREATED,
    summary="Discover a system context from selected evidence",
    responses={
        401: {"description": "Authentication required"},
        403: {"description": "Denied"},
        404: {"description": "System or source not found"},
        409: {"description": "Discovery conflict"},
        422: {"description": "Validation error"},
        503: {"description": "Discovery dependency unavailable"},
    },
)
async def start_discovery(
    request: Request,
    system_id: UUID,
    body: StartDiscoveryRequest,
    tenant_id: Annotated[UUID, Header(alias="X-Holospan-Tenant-ID")],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=128)],
    authenticated: Annotated[AuthenticatedRequest, Depends(current_tenant_request)],
    identities: Annotated[IdentityService, Depends(identity_service)],
    service: Annotated[AssuranceGenerationService, Depends(assurance_generation_service)],
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> Envelope[DiscoveryRunDetail]:
    await identities.verify_csrf(authenticated, csrf_header, request_id=request.state.request_id)
    return Envelope(
        data=await service.start_discovery(
            authenticated=authenticated,
            tenant_id=tenant_id,
            system_id=system_id,
            request=body,
            idempotency_key=idempotency_key,
            request_id=request.state.request_id,
        ),
        meta=response_meta(request),
    )


@router.get(
    "/assurance-generation/runs/{run_id}",
    response_model=Envelope[DiscoveryRunDetail],
    summary="Get an assurance-generation run",
)
async def get_run(
    request: Request,
    run_id: UUID,
    tenant_id: Annotated[UUID, Header(alias="X-Holospan-Tenant-ID")],
    authenticated: Annotated[AuthenticatedRequest, Depends(current_tenant_request)],
    service: Annotated[AssuranceGenerationService, Depends(assurance_generation_service)],
) -> Envelope[DiscoveryRunDetail]:
    return Envelope(
        data=await service.get_run(
            authenticated=authenticated,
            tenant_id=tenant_id,
            run_id=run_id,
            request_id=request.state.request_id,
        ),
        meta=response_meta(request),
    )


@router.get(
    "/systems/{system_id}/context-snapshots",
    response_model=Envelope[ContextSnapshotList],
    summary="List reviewed and draft context snapshots",
)
async def list_context_snapshots(
    request: Request,
    system_id: UUID,
    tenant_id: Annotated[UUID, Header(alias="X-Holospan-Tenant-ID")],
    authenticated: Annotated[AuthenticatedRequest, Depends(current_tenant_request)],
    service: Annotated[AssuranceGenerationService, Depends(assurance_generation_service)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> Envelope[ContextSnapshotList]:
    return Envelope(
        data=await service.list_context_snapshots(
            authenticated=authenticated,
            tenant_id=tenant_id,
            system_id=system_id,
            limit=limit,
            request_id=request.state.request_id,
        ),
        meta=response_meta(request),
    )


@router.post(
    "/context-snapshots/{snapshot_id}/review",
    response_model=Envelope[ContextSnapshotSummary],
    summary="Approve or reject a discovered context snapshot",
    responses={
        401: {"description": "Authentication required"},
        403: {"description": "Denied"},
        404: {"description": "Context not found"},
        409: {"description": "Quality or optimistic-lock conflict"},
    },
)
async def review_context(
    request: Request,
    snapshot_id: UUID,
    body: ReviewContextRequest,
    tenant_id: Annotated[UUID, Header(alias="X-Holospan-Tenant-ID")],
    authenticated: Annotated[AuthenticatedRequest, Depends(current_tenant_request)],
    identities: Annotated[IdentityService, Depends(identity_service)],
    service: Annotated[AssuranceGenerationService, Depends(assurance_generation_service)],
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> Envelope[ContextSnapshotSummary]:
    await identities.verify_csrf(authenticated, csrf_header, request_id=request.state.request_id)
    return Envelope(
        data=await service.review_context(
            authenticated=authenticated,
            tenant_id=tenant_id,
            snapshot_id=snapshot_id,
            request=body,
            request_id=request.state.request_id,
        ),
        meta=response_meta(request),
    )
