from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from holospan_api.core.config import get_settings
from holospan_api.core.database import tenant_database_session
from holospan_api.domains.identity_access.dependencies import identity_service
from holospan_api.domains.identity_access.service import IdentityService
from holospan_api.domains.system_context.service import SystemContextService
from holospan_api.domains.system_context.storage import ObjectStorage
from holospan_api.infrastructure.object_storage import S3CompatibleObjectStorage


@lru_cache
def object_storage() -> ObjectStorage:
    settings = get_settings()
    return S3CompatibleObjectStorage(
        endpoint=settings.object_storage_endpoint,
        access_key=settings.object_storage_access_key,
        secret_key=settings.object_storage_secret_key.get_secret_value(),
        secure=settings.object_storage_secure,
        region=settings.object_storage_region,
        connect_timeout_seconds=settings.object_storage_connect_timeout_seconds,
        read_timeout_seconds=settings.object_storage_read_timeout_seconds,
    )


async def system_context_service(
    session: Annotated[AsyncSession, Depends(tenant_database_session)],
    identities: Annotated[IdentityService, Depends(identity_service)],
    storage: Annotated[ObjectStorage, Depends(object_storage)],
) -> SystemContextService:
    settings = get_settings()
    return SystemContextService(
        session=session,
        identity_service=identities,
        object_storage=storage,
        source_bucket=settings.object_storage_bucket,
    )
