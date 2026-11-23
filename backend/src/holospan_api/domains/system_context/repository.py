from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from holospan_api.domains.identity_access.authorization import Actor
from holospan_api.domains.identity_access.models import AuditOutcome, AuthorizationAuditOutbox
from holospan_api.domains.system_context.contracts import CreateSystemRequest
from holospan_api.domains.system_context.models import SourceKind, SourceRecord, SystemRecord


class SystemContextRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_systems(self, *, tenant_id: UUID, limit: int) -> list[SystemRecord]:
        return list(
            (
                await self.session.scalars(
                    select(SystemRecord)
                    .where(SystemRecord.tenant_id == tenant_id)
                    .order_by(SystemRecord.created_at.desc(), SystemRecord.id.desc())
                    .limit(limit)
                )
            ).all()
        )

    async def get_system(self, *, tenant_id: UUID, system_id: UUID) -> SystemRecord | None:
        return await self.session.scalar(
            select(SystemRecord).where(
                SystemRecord.tenant_id == tenant_id,
                SystemRecord.id == system_id,
            )
        )

    async def list_sources(
        self,
        *,
        tenant_id: UUID,
        system_id: UUID,
        limit: int,
    ) -> list[SourceRecord]:
        return list(
            (
                await self.session.scalars(
                    select(SourceRecord)
                    .where(
                        SourceRecord.tenant_id == tenant_id,
                        SourceRecord.system_id == system_id,
                    )
                    .order_by(SourceRecord.created_at.desc(), SourceRecord.id.desc())
                    .limit(limit)
                )
            ).all()
        )

    async def create_system(
        self,
        *,
        tenant_id: UUID,
        actor: Actor,
        request: CreateSystemRequest,
        request_id: str,
    ) -> SystemRecord:
        record = SystemRecord(
            tenant_id=tenant_id,
            display_name=request.display_name,
            slug=request.slug,
            description=request.description,
            system_type=request.system_type,
            lifecycle_stage=request.lifecycle_stage,
            created_by=actor.principal_id,
        )
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        self.session.add(
            AuthorizationAuditOutbox(
                stream="tenant",
                tenant_id=tenant_id,
                actor_principal_id=actor.principal_id,
                action="system_context.system.create",
                target_type="system",
                target_id=str(record.id),
                outcome=AuditOutcome.SUCCEEDED,
                reason_code="SYSTEM_CREATED",
                request_id=request_id,
                principal_type="human",
                session_type="tenant",
                policy_version="system-context-v1",
                event_metadata={
                    "systemType": request.system_type.value,
                    "lifecycleStage": request.lifecycle_stage.value,
                },
                occurred_at=datetime.now(UTC),
            )
        )
        await self.session.flush()
        return record

    async def create_source(
        self,
        *,
        id: UUID,
        tenant_id: UUID,
        system_id: UUID,
        actor: Actor,
        kind: SourceKind,
        original_filename: str,
        declared_media_type: str,
        detected_media_type: str,
        byte_size: int,
        sha256: str,
        storage_bucket: str,
        object_key: str,
        request_id: str,
    ) -> SourceRecord:
        record = SourceRecord(
            id=id,
            tenant_id=tenant_id,
            system_id=system_id,
            kind=kind,
            original_filename=original_filename,
            declared_media_type=declared_media_type,
            detected_media_type=detected_media_type,
            byte_size=byte_size,
            sha256=sha256,
            storage_bucket=storage_bucket,
            object_key=object_key,
            created_by=actor.principal_id,
        )
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record)
        self.session.add(
            AuthorizationAuditOutbox(
                stream="tenant",
                tenant_id=tenant_id,
                actor_principal_id=actor.principal_id,
                action="system_context.source.create",
                target_type="system_source",
                target_id=str(record.id),
                outcome=AuditOutcome.SUCCEEDED,
                reason_code="SYSTEM_SOURCE_CREATED",
                request_id=request_id,
                principal_type="human",
                session_type="tenant",
                policy_version="system-context-v1",
                event_metadata={
                    "systemId": str(system_id),
                    "sourceKind": kind.value,
                    "sha256": sha256,
                    "byteSize": byte_size,
                    "detectedMediaType": detected_media_type,
                },
                occurred_at=datetime.now(UTC),
            )
        )
        await self.session.flush()
        return record
