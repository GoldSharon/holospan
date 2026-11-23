import asyncio
import hashlib
import json
from typing import Any
from uuid import UUID, uuid4

import structlog
from holospan_assurance.contracts import DiscoveryRequest, EvidenceSegment
from holospan_assurance.workflow import AssuranceDiscoveryWorkflow
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from holospan_api.domains.assurance_generation.contracts import (
    ContextSnapshotList,
    ContextSnapshotSummary,
    DiscoveryRunDetail,
    ReviewContextRequest,
    StartDiscoveryRequest,
)
from holospan_api.domains.assurance_generation.repository import AssuranceGenerationRepository
from holospan_api.domains.identity_access.errors import IdentityProblem
from holospan_api.domains.identity_access.service import AuthenticatedRequest, IdentityService
from holospan_api.domains.system_context.storage import ObjectStorage, ObjectStorageUnavailable

MAX_DISCOVERY_BYTES = 8 * 1024 * 1024
logger = structlog.get_logger()


class AssuranceGenerationService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        identity_service: IdentityService,
        object_storage: ObjectStorage,
        context_bucket: str,
        workflow: AssuranceDiscoveryWorkflow | None = None,
    ) -> None:
        self.session = session
        self.identity_service = identity_service
        self.object_storage = object_storage
        self.context_bucket = context_bucket
        self.workflow = workflow or AssuranceDiscoveryWorkflow()
        self.repository = AssuranceGenerationRepository(session)

    async def start_discovery(
        self,
        *,
        authenticated: AuthenticatedRequest,
        tenant_id: UUID,
        system_id: UUID,
        request: StartDiscoveryRequest,
        idempotency_key: str,
        request_id: str,
    ) -> DiscoveryRunDetail:
        await self.identity_service.authorize_tenant(
            authenticated,
            tenant_id,
            permission="assurance_generation.context.generate",
            request_id=request_id,
        )
        if not 16 <= len(idempotency_key) <= 128:
            raise IdentityProblem(
                422,
                "IDEMPOTENCY_KEY_INVALID",
                "A valid idempotency key is required.",
            )
        try:
            existing = await self.repository.get_existing_run(
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
            )
            if existing is not None:
                snapshot = await self.repository.get_snapshot_for_run(
                    tenant_id=tenant_id,
                    run_id=existing.id,
                )
                return self._run_detail(existing, snapshot)

            system = await self.repository.get_system(tenant_id=tenant_id, system_id=system_id)
            if system is None:
                raise IdentityProblem(
                    404, "SYSTEM_NOT_FOUND", "The requested system was not found."
                )
            sources = await self.repository.get_sources(
                tenant_id=tenant_id,
                system_id=system_id,
                source_ids=request.source_ids,
            )
        except IdentityProblem:
            raise
        except SQLAlchemyError as exc:
            await self.session.rollback()
            raise IdentityProblem(
                503,
                "ASSURANCE_GENERATION_UNAVAILABLE",
                "Assurance discovery is temporarily unavailable.",
            ) from exc

        if {source.id for source in sources} != set(request.source_ids):
            raise IdentityProblem(404, "SOURCE_NOT_FOUND", "A selected source was not found.")

        segments: list[EvidenceSegment] = []
        total_bytes = 0
        for source in sources:
            try:
                content = await self.object_storage.get_object(
                    bucket=source.storage_bucket,
                    object_key=source.object_key,
                    max_bytes=2 * 1024 * 1024,
                )
            except ObjectStorageUnavailable as exc:
                raise IdentityProblem(
                    503,
                    "SOURCE_STORAGE_UNAVAILABLE",
                    "Source evidence is temporarily unavailable.",
                ) from exc
            total_bytes += len(content)
            if total_bytes > MAX_DISCOVERY_BYTES:
                raise IdentityProblem(
                    413,
                    "DISCOVERY_INPUT_TOO_LARGE",
                    "The selected evidence exceeds the discovery budget.",
                )
            content_sha256 = hashlib.sha256(content).hexdigest()
            if content_sha256 != source.sha256:
                raise IdentityProblem(
                    409,
                    "SOURCE_INTEGRITY_FAILED",
                    "Stored source evidence no longer matches its attributed digest.",
                )
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise IdentityProblem(
                    422,
                    "SOURCE_CONTENT_INVALID",
                    "Discovery currently accepts UTF-8 text evidence only.",
                ) from exc
            line_count = max(1, len(text.splitlines()))
            segments.append(
                EvidenceSegment(
                    source_id=source.id,
                    source_sha256=source.sha256,
                    source_name=source.original_filename,
                    source_kind=source.kind.value,
                    locator=f"lines:1-{line_count}",
                    content=text,
                )
            )

        result = await asyncio.to_thread(
            self.workflow.run,
            DiscoveryRequest(
                tenant_id=tenant_id,
                system_id=system_id,
                system_name=system.display_name,
                segments=segments,
            ),
        )
        run_id = uuid4()
        snapshot_id = uuid4()
        object_key = (
            f"tenants/{tenant_id}/systems/{system_id}/assurance/context-snapshot/"
            f"{snapshot_id}/context.json"
        )
        context_bytes = json.dumps(
            result.snapshot.model_dump(mode="json", exclude={"content_sha256"}),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        try:
            await self.object_storage.put_object(
                bucket=self.context_bucket,
                object_key=object_key,
                data=context_bytes,
                content_type="application/json",
                sha256=result.snapshot.content_sha256,
            )
        except ObjectStorageUnavailable as exc:
            raise IdentityProblem(
                503,
                "CONTEXT_STORAGE_UNAVAILABLE",
                "Generated context storage is temporarily unavailable.",
            ) from exc

        source_manifest = [
            {
                "sourceId": str(source.id),
                "sha256": source.sha256,
                "kind": source.kind.value,
            }
            for source in sources
        ]
        try:
            run, snapshot = await self.repository.persist_discovery_result(
                run_id=run_id,
                snapshot_id=snapshot_id,
                tenant_id=tenant_id,
                system_id=system_id,
                actor=authenticated.actor,
                source_manifest=source_manifest,
                budget_profile=request.budget_profile,
                idempotency_key=idempotency_key,
                result=result,
                storage_bucket=self.context_bucket,
                object_key=object_key,
                request_id=request_id,
            )
            await self.session.commit()
            return self._run_detail(run, snapshot)
        except IntegrityError as exc:
            await self.session.rollback()
            diagnostic = getattr(getattr(exc, "orig", None), "diag", None)
            logger.warning(
                "assurance_discovery_integrity_conflict",
                constraint=getattr(diagnostic, "constraint_name", None),
                sqlstate=getattr(getattr(exc, "orig", None), "sqlstate", None),
                request_id=request_id,
            )
            existing = await self.repository.get_existing_run(
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
            )
            if existing is not None:
                await self._delete_context_object(object_key)
                snapshot = await self.repository.get_snapshot_for_run(
                    tenant_id=tenant_id,
                    run_id=existing.id,
                )
                return self._run_detail(existing, snapshot)
            await self._delete_context_object(object_key)
            raise IdentityProblem(
                409,
                "DISCOVERY_CONFLICT",
                "A discovery run changed concurrently. Retry with a new idempotency key.",
            ) from None
        except SQLAlchemyError as exc:
            await self.session.rollback()
            await self._delete_context_object(object_key)
            raise IdentityProblem(
                503,
                "ASSURANCE_GENERATION_UNAVAILABLE",
                "The generated context could not be recorded.",
            ) from exc

    async def get_run(
        self,
        *,
        authenticated: AuthenticatedRequest,
        tenant_id: UUID,
        run_id: UUID,
        request_id: str,
    ) -> DiscoveryRunDetail:
        await self.identity_service.authorize_tenant(
            authenticated,
            tenant_id,
            permission="assurance_generation.context.read",
            request_id=request_id,
        )
        try:
            run = await self.repository.get_run(tenant_id=tenant_id, run_id=run_id)
            if run is None:
                raise IdentityProblem(404, "DISCOVERY_RUN_NOT_FOUND", "The run was not found.")
            snapshot = await self.repository.get_snapshot_for_run(
                tenant_id=tenant_id,
                run_id=run.id,
            )
            return self._run_detail(run, snapshot)
        except IdentityProblem:
            raise
        except SQLAlchemyError as exc:
            await self.session.rollback()
            raise IdentityProblem(
                503,
                "ASSURANCE_GENERATION_UNAVAILABLE",
                "Assurance discovery is temporarily unavailable.",
            ) from exc

    async def list_context_snapshots(
        self,
        *,
        authenticated: AuthenticatedRequest,
        tenant_id: UUID,
        system_id: UUID,
        limit: int,
        request_id: str,
    ) -> ContextSnapshotList:
        await self.identity_service.authorize_tenant(
            authenticated,
            tenant_id,
            permission="assurance_generation.context.read",
            request_id=request_id,
        )
        try:
            system = await self.repository.get_system(tenant_id=tenant_id, system_id=system_id)
            if system is None:
                raise IdentityProblem(
                    404, "SYSTEM_NOT_FOUND", "The requested system was not found."
                )
            snapshots = await self.repository.list_snapshots(
                tenant_id=tenant_id,
                system_id=system_id,
                limit=limit,
            )
            return ContextSnapshotList(items=[self._snapshot_summary(item) for item in snapshots])
        except IdentityProblem:
            raise
        except SQLAlchemyError as exc:
            await self.session.rollback()
            raise IdentityProblem(
                503,
                "ASSURANCE_GENERATION_UNAVAILABLE",
                "Context snapshots are temporarily unavailable.",
            ) from exc

    async def review_context(
        self,
        *,
        authenticated: AuthenticatedRequest,
        tenant_id: UUID,
        snapshot_id: UUID,
        request: ReviewContextRequest,
        request_id: str,
    ) -> ContextSnapshotSummary:
        await self.identity_service.authorize_tenant(
            authenticated,
            tenant_id,
            permission="assurance_generation.context.review",
            request_id=request_id,
        )
        try:
            snapshot = await self.repository.get_snapshot(
                tenant_id=tenant_id,
                snapshot_id=snapshot_id,
            )
            if snapshot is None:
                raise IdentityProblem(
                    404, "CONTEXT_SNAPSHOT_NOT_FOUND", "The context was not found."
                )
            critic_passed = bool(snapshot.critic.get("passed"))
            if request.decision == "approve" and (
                not critic_passed or float(snapshot.critic_score) < 0.9
            ):
                raise IdentityProblem(
                    409,
                    "CONTEXT_QUALITY_GATE_FAILED",
                    "The context cannot be approved until its quality gates pass.",
                )
            reviewed = await self.repository.review_snapshot(
                tenant_id=tenant_id,
                snapshot_id=snapshot_id,
                expected_version=request.expected_version,
                decision=request.decision,
                comment=request.comment,
                actor=authenticated.actor,
                request_id=request_id,
            )
            if reviewed is None:
                raise IdentityProblem(
                    409,
                    "CONTEXT_REVIEW_CONFLICT",
                    "The context changed or was already reviewed.",
                )
            await self.session.commit()
            return self._snapshot_summary(reviewed)
        except IdentityProblem:
            raise
        except SQLAlchemyError as exc:
            await self.session.rollback()
            raise IdentityProblem(
                503,
                "ASSURANCE_GENERATION_UNAVAILABLE",
                "The review could not be recorded.",
            ) from exc

    async def _delete_context_object(self, object_key: str) -> None:
        try:
            await self.object_storage.delete_object(
                bucket=self.context_bucket,
                object_key=object_key,
            )
        except ObjectStorageUnavailable:
            pass

    @classmethod
    def _run_detail(cls, run: Any, snapshot: Any | None) -> DiscoveryRunDetail:
        source_ids = [
            UUID(item["sourceId"] if isinstance(item, dict) else str(item))
            for item in run.source_manifest
        ]
        return DiscoveryRunDetail(
            id=run.id,
            system_id=run.system_id,
            status=str(run.status),
            current_stage=run.current_stage,
            source_ids=source_ids,
            context_snapshot=cls._snapshot_summary(snapshot) if snapshot is not None else None,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )

    @staticmethod
    def _snapshot_summary(snapshot: Any) -> ContextSnapshotSummary:
        return ContextSnapshotSummary(
            id=snapshot.id,
            system_id=snapshot.system_id,
            version=snapshot.version,
            row_version=snapshot.row_version,
            status=str(snapshot.status),
            sha256=snapshot.sha256,
            critic_score=float(snapshot.critic_score),
            content=snapshot.content,
            approved_by=snapshot.approved_by,
            approved_at=snapshot.approved_at,
            created_at=snapshot.created_at,
        )
