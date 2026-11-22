from uuid import UUID

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from holospan_api.domains.identity_access.errors import IdentityProblem
from holospan_api.domains.identity_access.service import AuthenticatedRequest, IdentityService
from holospan_api.domains.system_context.contracts import (
    CreateSystemRequest,
    SystemList,
    SystemSummary,
)
from holospan_api.domains.system_context.repository import SystemContextRepository


class SystemContextService:
    def __init__(self, *, session: AsyncSession, identity_service: IdentityService) -> None:
        self.session = session
        self.identity_service = identity_service
        self.repository = SystemContextRepository(session)

    async def list_systems(
        self,
        *,
        authenticated: AuthenticatedRequest,
        tenant_id: UUID,
        limit: int,
        request_id: str,
    ) -> SystemList:
        await self.identity_service.authorize_tenant(
            authenticated,
            tenant_id,
            permission="system_context.systems.read",
            request_id=request_id,
        )
        try:
            records = await self.repository.list_systems(tenant_id=tenant_id, limit=limit)
            return SystemList(items=[SystemSummary.model_validate(item) for item in records])
        except SQLAlchemyError as exc:
            await self.session.rollback()
            raise IdentityProblem(
                503,
                "SYSTEM_CONTEXT_UNAVAILABLE",
                "System information is temporarily unavailable.",
            ) from exc

    async def create_system(
        self,
        *,
        authenticated: AuthenticatedRequest,
        tenant_id: UUID,
        request: CreateSystemRequest,
        request_id: str,
    ) -> SystemSummary:
        await self.identity_service.authorize_tenant(
            authenticated,
            tenant_id,
            permission="system_context.systems.manage",
            request_id=request_id,
        )
        try:
            record = await self.repository.create_system(
                tenant_id=tenant_id,
                actor=authenticated.actor,
                request=request,
                request_id=request_id,
            )
            result = SystemSummary.model_validate(record)
            await self.session.commit()
            return result
        except IntegrityError as exc:
            await self.session.rollback()
            raise IdentityProblem(
                409,
                "SYSTEM_SLUG_CONFLICT",
                "A system with that slug already exists in this workspace.",
            ) from exc
        except SQLAlchemyError as exc:
            await self.session.rollback()
            raise IdentityProblem(
                503,
                "SYSTEM_CONTEXT_UNAVAILABLE",
                "System information is temporarily unavailable.",
            ) from exc
