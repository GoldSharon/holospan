from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from holospan_api.core.config import get_settings
from holospan_api.core.database import tenant_database_session
from holospan_api.domains.assurance_generation.service import AssuranceGenerationService
from holospan_api.domains.identity_access.dependencies import identity_service
from holospan_api.domains.identity_access.service import IdentityService
from holospan_api.domains.system_context.dependencies import object_storage
from holospan_api.domains.system_context.storage import ObjectStorage


async def assurance_generation_service(
    session: Annotated[AsyncSession, Depends(tenant_database_session)],
    identities: Annotated[IdentityService, Depends(identity_service)],
    storage: Annotated[ObjectStorage, Depends(object_storage)],
) -> AssuranceGenerationService:
    settings = get_settings()
    return AssuranceGenerationService(
        session=session,
        identity_service=identities,
        object_storage=storage,
        context_bucket=settings.assurance_context_bucket,
    )
