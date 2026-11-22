from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from holospan_api.core.database import tenant_database_session
from holospan_api.domains.identity_access.dependencies import identity_service
from holospan_api.domains.identity_access.service import IdentityService
from holospan_api.domains.system_context.service import SystemContextService


async def system_context_service(
    session: Annotated[AsyncSession, Depends(tenant_database_session)],
    identities: Annotated[IdentityService, Depends(identity_service)],
) -> SystemContextService:
    return SystemContextService(session=session, identity_service=identities)
