import hashlib
from pathlib import PurePath
from uuid import UUID, uuid4

import structlog
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from holospan_api.domains.identity_access.errors import IdentityProblem
from holospan_api.domains.identity_access.service import AuthenticatedRequest, IdentityService
from holospan_api.domains.system_context.contracts import (
    CreateSystemRequest,
    SourceList,
    SourceSummary,
    SystemList,
    SystemSummary,
)
from holospan_api.domains.system_context.models import SourceKind
from holospan_api.domains.system_context.repository import SystemContextRepository
from holospan_api.domains.system_context.storage import ObjectStorage, ObjectStorageUnavailable

logger = structlog.get_logger()

MAX_SOURCE_BYTES = 2 * 1024 * 1024
SOURCE_MEDIA_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".json": "application/json",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
}


class SystemContextService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        identity_service: IdentityService,
        object_storage: ObjectStorage | None = None,
        source_bucket: str = "holospan-raw",
    ) -> None:
        self.session = session
        self.identity_service = identity_service
        self.repository = SystemContextRepository(session)
        self.object_storage = object_storage
        self.source_bucket = source_bucket

    async def get_system(
        self,
        *,
        authenticated: AuthenticatedRequest,
        tenant_id: UUID,
        system_id: UUID,
        request_id: str,
    ) -> SystemSummary:
        await self.identity_service.authorize_tenant(
            authenticated,
            tenant_id,
            permission="system_context.systems.read",
            request_id=request_id,
        )
        try:
            record = await self.repository.get_system(tenant_id=tenant_id, system_id=system_id)
            if record is None:
                raise IdentityProblem(
                    404,
                    "SYSTEM_NOT_FOUND",
                    "The requested system was not found.",
                )
            return SystemSummary.model_validate(record)
        except IdentityProblem:
            raise
        except SQLAlchemyError as exc:
            await self.session.rollback()
            raise IdentityProblem(
                503,
                "SYSTEM_CONTEXT_UNAVAILABLE",
                "System information is temporarily unavailable.",
            ) from exc

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

    async def list_sources(
        self,
        *,
        authenticated: AuthenticatedRequest,
        tenant_id: UUID,
        system_id: UUID,
        limit: int,
        request_id: str,
    ) -> SourceList:
        await self.identity_service.authorize_tenant(
            authenticated,
            tenant_id,
            permission="system_context.sources.read",
            request_id=request_id,
        )
        try:
            system = await self.repository.get_system(tenant_id=tenant_id, system_id=system_id)
            if system is None:
                raise IdentityProblem(
                    404,
                    "SYSTEM_NOT_FOUND",
                    "The requested system was not found.",
                )
            records = await self.repository.list_sources(
                tenant_id=tenant_id,
                system_id=system_id,
                limit=limit,
            )
            return SourceList(items=[SourceSummary.model_validate(item) for item in records])
        except IdentityProblem:
            raise
        except SQLAlchemyError as exc:
            await self.session.rollback()
            raise IdentityProblem(
                503,
                "SYSTEM_CONTEXT_UNAVAILABLE",
                "Source information is temporarily unavailable.",
            ) from exc

    async def create_source(
        self,
        *,
        authenticated: AuthenticatedRequest,
        tenant_id: UUID,
        system_id: UUID,
        kind: SourceKind,
        original_filename: str,
        declared_media_type: str,
        content: bytes,
        request_id: str,
    ) -> SourceSummary:
        await self.identity_service.authorize_tenant(
            authenticated,
            tenant_id,
            permission="system_context.sources.manage",
            request_id=request_id,
        )
        try:
            system = await self.repository.get_system(tenant_id=tenant_id, system_id=system_id)
        except SQLAlchemyError as exc:
            await self.session.rollback()
            raise IdentityProblem(
                503,
                "SYSTEM_CONTEXT_UNAVAILABLE",
                "System information is temporarily unavailable.",
            ) from exc
        if system is None:
            raise IdentityProblem(404, "SYSTEM_NOT_FOUND", "The requested system was not found.")

        filename, detected_media_type = self._validate_source(
            original_filename=original_filename,
            declared_media_type=declared_media_type,
            content=content,
        )
        if self.object_storage is None:
            raise IdentityProblem(
                503,
                "SOURCE_STORAGE_UNAVAILABLE",
                "Source storage is temporarily unavailable.",
            )

        source_id = uuid4()
        digest = hashlib.sha256(content).hexdigest()
        object_key = (
            f"tenants/{tenant_id}/systems/{system_id}/sources/{source_id}/raw"
        )
        try:
            await self.object_storage.put_object(
                bucket=self.source_bucket,
                object_key=object_key,
                data=content,
                content_type=detected_media_type,
                sha256=digest,
            )
        except ObjectStorageUnavailable as exc:
            raise IdentityProblem(
                503,
                "SOURCE_STORAGE_UNAVAILABLE",
                "Source storage is temporarily unavailable.",
            ) from exc

        try:
            record = await self.repository.create_source(
                id=source_id,
                tenant_id=tenant_id,
                system_id=system_id,
                actor=authenticated.actor,
                kind=kind,
                original_filename=filename,
                declared_media_type=declared_media_type,
                detected_media_type=detected_media_type,
                byte_size=len(content),
                sha256=digest,
                storage_bucket=self.source_bucket,
                object_key=object_key,
                request_id=request_id,
            )
            result = SourceSummary.model_validate(record)
            await self.session.commit()
            return result
        except SQLAlchemyError as exc:
            await self.session.rollback()
            try:
                await self.object_storage.delete_object(
                    bucket=self.source_bucket,
                    object_key=object_key,
                )
            except ObjectStorageUnavailable:
                logger.warning(
                    "system_source_cleanup_failed",
                    source_id=str(source_id),
                    system_id=str(system_id),
                    tenant_id=str(tenant_id),
                )
            raise IdentityProblem(
                503,
                "SYSTEM_CONTEXT_UNAVAILABLE",
                "The source could not be recorded.",
            ) from exc

    @staticmethod
    def _validate_source(
        *,
        original_filename: str,
        declared_media_type: str,
        content: bytes,
    ) -> tuple[str, str]:
        if len(content) > MAX_SOURCE_BYTES:
            raise IdentityProblem(413, "SOURCE_TOO_LARGE", "The source exceeds the 2 MiB limit.")
        if not content:
            raise IdentityProblem(422, "SOURCE_TYPE_UNSUPPORTED", "The source file is empty.")
        filename = original_filename.strip()
        if (
            not filename
            or len(filename) > 255
            or filename != PurePath(filename).name
            or "\\" in filename
            or any(ord(character) < 32 for character in filename)
        ):
            raise IdentityProblem(
                422,
                "SOURCE_TYPE_UNSUPPORTED",
                "The source filename is not supported.",
            )
        detected_media_type = SOURCE_MEDIA_TYPES.get(PurePath(filename).suffix.lower())
        if detected_media_type is None or b"\x00" in content:
            raise IdentityProblem(
                422,
                "SOURCE_TYPE_UNSUPPORTED",
                "Only supported text documents and API contracts can be uploaded.",
            )
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise IdentityProblem(
                422,
                "SOURCE_TYPE_UNSUPPORTED",
                "Only UTF-8 text sources can be uploaded.",
            ) from exc
        if (
            not declared_media_type
            or len(declared_media_type) > 127
            or "/" not in declared_media_type
            or any(ord(character) < 32 or ord(character) > 126 for character in declared_media_type)
        ):
            raise IdentityProblem(
                422,
                "SOURCE_TYPE_UNSUPPORTED",
                "The declared source media type is not supported.",
            )
        return filename, detected_media_type
