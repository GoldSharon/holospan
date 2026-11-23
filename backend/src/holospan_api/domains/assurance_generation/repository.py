from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from holospan_assurance.contracts import DiscoveryResult
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from holospan_api.domains.assurance_generation.models import (
    AssuranceArtifactCitationRecord,
    AssuranceContextClaimRecord,
    AssuranceContextSnapshotRecord,
    AssuranceGenerationRunRecord,
    AssuranceRunStatus,
    ContextClaimStatus,
    ContextSnapshotStatus,
)
from holospan_api.domains.identity_access.authorization import Actor
from holospan_api.domains.identity_access.models import AuditOutcome, AuthorizationAuditOutbox
from holospan_api.domains.system_context.models import SourceRecord, SystemRecord


class AssuranceGenerationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_system(self, *, tenant_id: UUID, system_id: UUID) -> SystemRecord | None:
        return await self.session.scalar(
            select(SystemRecord).where(
                SystemRecord.tenant_id == tenant_id,
                SystemRecord.id == system_id,
            )
        )

    async def get_sources(
        self,
        *,
        tenant_id: UUID,
        system_id: UUID,
        source_ids: list[UUID],
    ) -> list[SourceRecord]:
        return list(
            (
                await self.session.scalars(
                    select(SourceRecord)
                    .where(
                        SourceRecord.tenant_id == tenant_id,
                        SourceRecord.system_id == system_id,
                        SourceRecord.id.in_(source_ids),
                    )
                    .order_by(SourceRecord.created_at, SourceRecord.id)
                )
            ).all()
        )

    async def get_existing_run(
        self,
        *,
        tenant_id: UUID,
        idempotency_key: str,
    ) -> AssuranceGenerationRunRecord | None:
        return await self.session.scalar(
            select(AssuranceGenerationRunRecord).where(
                AssuranceGenerationRunRecord.tenant_id == tenant_id,
                AssuranceGenerationRunRecord.idempotency_key == idempotency_key,
            )
        )

    async def get_run(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
    ) -> AssuranceGenerationRunRecord | None:
        return await self.session.scalar(
            select(AssuranceGenerationRunRecord).where(
                AssuranceGenerationRunRecord.tenant_id == tenant_id,
                AssuranceGenerationRunRecord.id == run_id,
            )
        )

    async def get_snapshot(
        self,
        *,
        tenant_id: UUID,
        snapshot_id: UUID,
    ) -> AssuranceContextSnapshotRecord | None:
        return await self.session.scalar(
            select(AssuranceContextSnapshotRecord).where(
                AssuranceContextSnapshotRecord.tenant_id == tenant_id,
                AssuranceContextSnapshotRecord.id == snapshot_id,
            )
        )

    async def get_snapshot_for_run(
        self,
        *,
        tenant_id: UUID,
        run_id: UUID,
    ) -> AssuranceContextSnapshotRecord | None:
        return await self.session.scalar(
            select(AssuranceContextSnapshotRecord).where(
                AssuranceContextSnapshotRecord.tenant_id == tenant_id,
                AssuranceContextSnapshotRecord.run_id == run_id,
            )
        )

    async def list_snapshots(
        self,
        *,
        tenant_id: UUID,
        system_id: UUID,
        limit: int,
    ) -> list[AssuranceContextSnapshotRecord]:
        return list(
            (
                await self.session.scalars(
                    select(AssuranceContextSnapshotRecord)
                    .where(
                        AssuranceContextSnapshotRecord.tenant_id == tenant_id,
                        AssuranceContextSnapshotRecord.system_id == system_id,
                    )
                    .order_by(
                        AssuranceContextSnapshotRecord.created_at.desc(),
                        AssuranceContextSnapshotRecord.id.desc(),
                    )
                    .limit(limit)
                )
            ).all()
        )

    async def persist_discovery_result(
        self,
        *,
        run_id: UUID,
        snapshot_id: UUID,
        tenant_id: UUID,
        system_id: UUID,
        actor: Actor,
        source_manifest: list[dict[str, Any]],
        budget_profile: str,
        idempotency_key: str,
        result: DiscoveryResult,
        storage_bucket: str,
        object_key: str,
        request_id: str,
    ) -> tuple[AssuranceGenerationRunRecord, AssuranceContextSnapshotRecord]:
        next_version = (
            await self.session.scalar(
                select(func.coalesce(func.max(AssuranceContextSnapshotRecord.version), 0)).where(
                    AssuranceContextSnapshotRecord.tenant_id == tenant_id,
                    AssuranceContextSnapshotRecord.system_id == system_id,
                )
            )
        ) or 0
        snapshot = AssuranceContextSnapshotRecord(
            id=snapshot_id,
            tenant_id=tenant_id,
            system_id=system_id,
            run_id=run_id,
            version=int(next_version) + 1,
            row_version=1,
            status=ContextSnapshotStatus.DRAFT,
            schema_version=result.snapshot.schema_version,
            content=result.snapshot.model_dump(mode="json"),
            sha256=result.snapshot.content_sha256,
            storage_bucket=storage_bucket,
            object_key=object_key,
            critic_score=result.critic.score,
            critic=result.critic.model_dump(mode="json"),
        )
        run = AssuranceGenerationRunRecord(
            id=run_id,
            tenant_id=tenant_id,
            system_id=system_id,
            status=(
                AssuranceRunStatus.CONTEXT_REVIEW
                if result.critic.passed
                else AssuranceRunStatus.PAUSED
            ),
            current_stage="review_context" if result.critic.passed else "context_quality_failed",
            source_manifest=source_manifest,
            budget_profile=budget_profile,
            budget_state={"modelCalls": 0, "tokens": 0, "cost": 0},
            workflow_version="discovery-v1",
            idempotency_key=idempotency_key,
            context_snapshot_id=snapshot_id,
            created_by=actor.principal_id,
        )
        self.session.add(run)
        await self.session.flush()
        self.session.add(snapshot)
        await self.session.flush()

        for claim in result.snapshot.claims:
            claim_record = AssuranceContextClaimRecord(
                tenant_id=tenant_id,
                system_id=system_id,
                run_id=run_id,
                snapshot_id=snapshot_id,
                subject_key=claim.subject_key,
                claim_type=claim.claim_type,
                value=claim.value,
                status=ContextClaimStatus(claim.status),
                confidence=claim.confidence,
                extraction_method=claim.extraction_method,
            )
            self.session.add(claim_record)
            await self.session.flush()
            for citation in claim.citations:
                self.session.add(
                    AssuranceArtifactCitationRecord(
                        tenant_id=tenant_id,
                        system_id=system_id,
                        artifact_type="context_claim",
                        artifact_id=claim_record.id,
                        source_id=citation.source_id,
                        locator_type="line_range",
                        locator=citation.locator,
                        content_sha256=citation.content_sha256,
                    )
                )

        self.session.add(
            AuthorizationAuditOutbox(
                stream="tenant",
                tenant_id=tenant_id,
                actor_principal_id=actor.principal_id,
                action="assurance_generation.context.discover",
                target_type="context_snapshot",
                target_id=str(snapshot_id),
                outcome=AuditOutcome.SUCCEEDED,
                reason_code=(
                    "CONTEXT_READY_FOR_REVIEW"
                    if result.critic.passed
                    else "CONTEXT_QUALITY_GATE_FAILED"
                ),
                request_id=request_id,
                principal_type="human",
                session_type="tenant",
                policy_version="assurance-discovery-v1",
                event_metadata={
                    "runId": str(run_id),
                    "systemId": str(system_id),
                    "sourceCount": len(source_manifest),
                    "contextSha256": result.snapshot.content_sha256,
                    "criticScore": result.critic.score,
                },
                occurred_at=datetime.now(UTC),
            )
        )
        await self.session.flush()
        await self.session.refresh(run)
        await self.session.refresh(snapshot)
        return run, snapshot

    async def review_snapshot(
        self,
        *,
        tenant_id: UUID,
        snapshot_id: UUID,
        expected_version: int,
        decision: str,
        comment: str,
        actor: Actor,
        request_id: str,
    ) -> AssuranceContextSnapshotRecord | None:
        now = datetime.now(UTC)
        status = (
            ContextSnapshotStatus.APPROVED
            if decision == "approve"
            else ContextSnapshotStatus.REJECTED
        )
        snapshot = await self.session.scalar(
            update(AssuranceContextSnapshotRecord)
            .where(
                AssuranceContextSnapshotRecord.tenant_id == tenant_id,
                AssuranceContextSnapshotRecord.id == snapshot_id,
                AssuranceContextSnapshotRecord.status == ContextSnapshotStatus.DRAFT,
                AssuranceContextSnapshotRecord.row_version == expected_version,
            )
            .values(
                status=status,
                row_version=AssuranceContextSnapshotRecord.row_version + 1,
                review_comment=comment,
                approved_by=actor.principal_id if decision == "approve" else None,
                approved_at=now if decision == "approve" else None,
            )
            .returning(AssuranceContextSnapshotRecord)
        )
        if snapshot is None:
            return None
        self.session.add(
            AuthorizationAuditOutbox(
                stream="tenant",
                tenant_id=tenant_id,
                actor_principal_id=actor.principal_id,
                action="assurance_generation.context.review",
                target_type="context_snapshot",
                target_id=str(snapshot_id),
                outcome=AuditOutcome.SUCCEEDED,
                reason_code=("CONTEXT_APPROVED" if decision == "approve" else "CONTEXT_REJECTED"),
                request_id=request_id,
                principal_type="human",
                session_type="tenant",
                policy_version="assurance-discovery-v1",
                event_metadata={
                    "systemId": str(snapshot.system_id),
                    "decision": decision,
                    "rowVersion": snapshot.row_version,
                },
                occurred_at=now,
            )
        )
        return cast(AssuranceContextSnapshotRecord, snapshot)
