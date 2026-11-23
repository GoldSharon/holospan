from typing import Any, cast
from uuid import uuid4

from holospan_assurance.contracts import DiscoveryRequest, EvidenceSegment
from holospan_assurance.workflow import AssuranceDiscoveryWorkflow
from sqlalchemy.ext.asyncio import AsyncSession
from system_context.test_service import authenticated_request

from holospan_api.domains.assurance_generation.repository import AssuranceGenerationRepository
from holospan_api.domains.identity_access.models import AuthorizationAuditOutbox


class RecordingSession:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.added: list[Any] = []

    async def scalar(self, _statement: object) -> int:
        return 0

    def add(self, value: Any) -> None:
        self.added.append(value)
        self.events.append(f"add:{type(value).__name__}")

    async def flush(self) -> None:
        self.events.append("flush")

    async def refresh(self, value: Any) -> None:
        self.events.append(f"refresh:{type(value).__name__}")


async def test_run_is_flushed_before_snapshot_and_audit_contract_is_complete() -> None:
    tenant_id = uuid4()
    system_id = uuid4()
    source_id = uuid4()
    session = RecordingSession()
    repository = AssuranceGenerationRepository(cast(AsyncSession, session))
    result = AssuranceDiscoveryWorkflow().run(
        DiscoveryRequest(
            tenant_id=tenant_id,
            system_id=system_id,
            system_name="Travel Agent",
            segments=[
                EvidenceSegment(
                    source_id=source_id,
                    source_sha256="a" * 64,
                    source_name="requirements.md",
                    source_kind="context_document",
                    locator="lines:1-2",
                    content="Agent: Planner\nCapability: Search hotels.",
                )
            ],
        )
    )

    await repository.persist_discovery_result(
        run_id=uuid4(),
        snapshot_id=uuid4(),
        tenant_id=tenant_id,
        system_id=system_id,
        actor=authenticated_request(tenant_id).actor,
        source_manifest=[{"sourceId": str(source_id), "sha256": "a" * 64}],
        budget_profile="balanced",
        idempotency_key="repository-order-v1",
        result=result,
        storage_bucket="holospan-evidence",
        object_key="tenants/test/context.json",
        request_id="request-repository-order",
    )

    assert session.events[:4] == [
        "add:AssuranceGenerationRunRecord",
        "flush",
        "add:AssuranceContextSnapshotRecord",
        "flush",
    ]
    audit = next(value for value in session.added if isinstance(value, AuthorizationAuditOutbox))
    assert audit.policy_version == "assurance-discovery-v1"
    assert audit.principal_type == "human"
    assert audit.session_type == "tenant"
    assert audit.event_metadata["contextSha256"] == result.snapshot.content_sha256
