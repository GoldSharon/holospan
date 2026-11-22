from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from holospan_api.domains.identity_access.authorization import Actor
from holospan_api.domains.identity_access.models import AuditOutcome, AuthorizationAuditOutbox
from holospan_api.domains.system_context.contracts import CreateSystemRequest
from holospan_api.domains.system_context.models import SystemRecord


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
