from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceCitation(FrozenContract):
    source_id: UUID
    locator: str = Field(min_length=1, max_length=512)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class EvidenceSegment(FrozenContract):
    source_id: UUID
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_name: str = Field(min_length=1, max_length=255)
    source_kind: Literal["context_document", "api_contract"]
    locator: str = Field(min_length=1, max_length=512)
    content: str = Field(min_length=1, max_length=2_097_152)


class EvidenceClaim(FrozenContract):
    subject_key: str = Field(min_length=1, max_length=255)
    claim_type: str = Field(min_length=1, max_length=128)
    value: Any
    status: Literal["supported", "conflicting", "unknown", "rejected"] = "supported"
    confidence: float = Field(ge=0, le=1)
    extraction_method: Literal["deterministic", "model", "human"] = "deterministic"
    citations: list[EvidenceCitation]


class ContextGap(FrozenContract):
    code: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=1000)
    source_id: UUID | None = None
    locator: str | None = Field(default=None, max_length=512)


class ComponentContext(FrozenContract):
    key: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    purpose: str | None = Field(default=None, max_length=2000)
    capabilities: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    policies: list[str] = Field(default_factory=list)


class ContextSnapshotCandidate(FrozenContract):
    tenant_id: UUID
    system_id: UUID
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    system_name: str = Field(min_length=1, max_length=255)
    status: Literal["draft"] = "draft"
    schema_version: Literal["1.0"] = "1.0"
    claims: list[EvidenceClaim]
    components: list[ComponentContext]
    gaps: list[ContextGap]
    generator: Literal["deterministic_discovery_v1"] = "deterministic_discovery_v1"
    content_sha256: str = Field(default="0" * 64, pattern=r"^[0-9a-f]{64}$")


class CriticResult(FrozenContract):
    score: float = Field(ge=0, le=1)
    passed: bool
    gates: dict[str, bool]
    issues: list[str]


class DiscoveryRequest(FrozenContract):
    tenant_id: UUID
    system_id: UUID
    system_name: str = Field(min_length=1, max_length=255)
    segments: list[EvidenceSegment] = Field(min_length=1, max_length=100)


class DiscoveryResult(FrozenContract):
    snapshot: ContextSnapshotCandidate
    critic: CriticResult
