import hashlib
import json
import re
from collections import defaultdict
from typing import Any

from holospan_assurance.contracts import (
    ComponentContext,
    ContextGap,
    ContextSnapshotCandidate,
    DiscoveryRequest,
    DiscoveryResult,
    EvidenceCitation,
    EvidenceClaim,
    EvidenceSegment,
)
from holospan_assurance.critic import ContextCritic

_CLAIM_PREFIXES = {
    "purpose": "purpose",
    "capability": "capability",
    "feature": "capability",
    "supports": "capability",
    "input": "input",
    "output": "output",
    "tool": "tool",
    "dependency": "dependency",
    "policy": "policy",
    "requirement": "requirement",
    "handoff": "handoff",
    "autonomy": "autonomy",
}
_UNTRUSTED_INSTRUCTION_PATTERNS = (
    re.compile(r"\bignore\s+(?:all\s+)?previous\s+instructions?\b", re.IGNORECASE),
    re.compile(r"\breveal\s+(?:the\s+)?system\s+prompt\b", re.IGNORECASE),
    re.compile(r"\b(?:call|run|execute)\s+(?:the\s+)?(?:shell|terminal|command)\b", re.IGNORECASE),
    re.compile(r"\bupload\s+(?:all\s+)?secrets?\b", re.IGNORECASE),
)


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized[:255] or "system"


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class AssuranceDiscoveryWorkflow:
    """Bounded discovery, synthesis, and deterministic context criticism."""

    def __init__(self, *, critic: ContextCritic | None = None) -> None:
        self.critic = critic or ContextCritic()

    def run(self, request: DiscoveryRequest) -> DiscoveryResult:
        source_manifest_sha256 = _canonical_hash(
            sorted(
                (
                    str(segment.source_id),
                    segment.source_sha256,
                    segment.source_kind,
                    segment.source_name,
                )
                for segment in request.segments
            )
        )
        claims: list[EvidenceClaim] = []
        gaps: list[ContextGap] = []
        component_names: dict[str, str] = {}

        for segment in request.segments:
            segment_claims, segment_gaps, names = self._discover_segment(segment)
            claims.extend(segment_claims)
            gaps.extend(segment_gaps)
            component_names.update(names)

        claims = self._deduplicate_claims(claims)
        components = self._synthesize_components(claims, component_names)
        if not claims:
            gaps.append(
                ContextGap(
                    code="NO_EVIDENCED_CLAIMS",
                    message=(
                        "No explicit capability, requirement, policy, or interface claim was found."
                    ),
                )
            )

        snapshot = ContextSnapshotCandidate(
            tenant_id=request.tenant_id,
            system_id=request.system_id,
            source_manifest_sha256=source_manifest_sha256,
            system_name=request.system_name,
            claims=claims,
            components=components,
            gaps=gaps,
        )
        content_sha256 = _canonical_hash(
            snapshot.model_dump(mode="json", exclude={"content_sha256"})
        )
        snapshot = snapshot.model_copy(update={"content_sha256": content_sha256})
        critic = self.critic.evaluate(
            snapshot,
            allowed_source_ids={segment.source_id for segment in request.segments},
        )
        return DiscoveryResult(snapshot=snapshot, critic=critic)

    def _discover_segment(
        self,
        segment: EvidenceSegment,
    ) -> tuple[list[EvidenceClaim], list[ContextGap], dict[str, str]]:
        claims: list[EvidenceClaim] = []
        gaps: list[ContextGap] = []
        component_names: dict[str, str] = {}
        subject_key = "system"

        for line_number, raw_line in enumerate(segment.content.splitlines(), start=1):
            line = raw_line.strip().lstrip("-* ").strip()
            if not line:
                continue
            locator = f"{segment.locator}#line:{line_number}"
            if any(pattern.search(line) for pattern in _UNTRUSTED_INSTRUCTION_PATTERNS):
                gaps.append(
                    ContextGap(
                        code="UNTRUSTED_INSTRUCTION_DETECTED",
                        message=(
                            "An instruction-like source line was excluded from discovery claims."
                        ),
                        source_id=segment.source_id,
                        locator=locator,
                    )
                )
                continue

            label, separator, value = line.partition(":")
            if not separator or not value.strip():
                continue
            normalized_label = label.strip().lower()
            normalized_value = value.strip()
            if normalized_label in {"agent", "component"}:
                subject_key = _slug(normalized_value)
                component_names[subject_key] = normalized_value
                continue
            claim_type = _CLAIM_PREFIXES.get(normalized_label)
            if claim_type is None:
                continue
            claims.append(
                EvidenceClaim(
                    subject_key=subject_key,
                    claim_type=claim_type,
                    value=normalized_value,
                    confidence=1.0,
                    citations=[
                        EvidenceCitation(
                            source_id=segment.source_id,
                            locator=locator,
                            content_sha256=segment.source_sha256,
                        )
                    ],
                )
            )

        api_claims, api_gaps, api_names = self._discover_openapi(segment)
        claims.extend(api_claims)
        gaps.extend(api_gaps)
        component_names.update(api_names)

        return claims, gaps, component_names

    @staticmethod
    def _discover_openapi(
        segment: EvidenceSegment,
    ) -> tuple[list[EvidenceClaim], list[ContextGap], dict[str, str]]:
        if segment.source_kind != "api_contract" or not re.search(
            r"(?:^|[\s{])['\"]?openapi['\"]?\s*:", segment.content, re.MULTILINE
        ):
            return [], [], {}

        title_match = re.search(
            r"^[ \t]*['\"]?title['\"]?[ \t]*:[ \t]*['\"]?([^'\"\r\n,}]+)",
            segment.content,
            re.MULTILINE,
        )
        title = title_match.group(1).strip() if title_match else segment.source_name
        subject_key = _slug(title)
        names = {subject_key: title}
        claims: list[EvidenceClaim] = []
        gaps: list[ContextGap] = []
        current_path: str | None = None
        current_method: str | None = None
        method_line = 1
        path_pattern = re.compile(r"^[ \t]*['\"]?(/[^'\"\s:]*)['\"]?[ \t]*:")
        method_pattern = re.compile(
            r"^[ \t]*['\"]?(get|post|put|patch|delete|options|head)['\"]?[ \t]*:",
            re.IGNORECASE,
        )
        description_pattern = re.compile(
            r"^[ \t]*['\"]?(summary|operationId)['\"]?[ \t]*:[ \t]*['\"]?"
            r"([^'\"\r\n,}]+)",
            re.IGNORECASE,
        )
        for line_number, raw_line in enumerate(segment.content.splitlines(), start=1):
            path_match = path_pattern.match(raw_line)
            if path_match:
                current_path = path_match.group(1)
                current_method = None
                continue
            method_match = method_pattern.match(raw_line)
            if method_match and current_path:
                current_method = method_match.group(1).upper()
                method_line = line_number
                continue
            description_match = description_pattern.match(raw_line)
            if not description_match or not current_path or not current_method:
                continue
            description_kind = description_match.group(1).lower()
            description = description_match.group(2).strip()
            if any(pattern.search(description) for pattern in _UNTRUSTED_INSTRUCTION_PATTERNS):
                gaps.append(
                    ContextGap(
                        code="UNTRUSTED_INSTRUCTION_DETECTED",
                        message=(
                            "An instruction-like API operation was excluded from discovery claims."
                        ),
                        source_id=segment.source_id,
                        locator=f"{segment.locator}#line:{line_number}",
                    )
                )
                continue
            prefix = f"{current_method} {current_path} —"
            claim = EvidenceClaim(
                subject_key=subject_key,
                claim_type="capability",
                value=f"{prefix} {description}",
                confidence=1.0,
                citations=[
                    EvidenceCitation(
                        source_id=segment.source_id,
                        locator=f"{segment.locator}#lines:{method_line}-{line_number}",
                        content_sha256=segment.source_sha256,
                    )
                ],
            )
            existing_index = next(
                (
                    index
                    for index, existing in enumerate(claims)
                    if str(existing.value).startswith(prefix)
                ),
                None,
            )
            if existing_index is None:
                claims.append(claim)
            elif description_kind == "summary":
                claims[existing_index] = claim

        if not claims:
            gaps.append(
                ContextGap(
                    code="OPENAPI_OPERATIONS_NOT_DESCRIBED",
                    message=(
                        "The API contract did not expose described operations "
                        "for capability discovery."
                    ),
                    source_id=segment.source_id,
                    locator=segment.locator,
                )
            )
        return claims, gaps, names

    @staticmethod
    def _deduplicate_claims(claims: list[EvidenceClaim]) -> list[EvidenceClaim]:
        unique: dict[tuple[str, str, str], EvidenceClaim] = {}
        for claim in claims:
            key = (claim.subject_key, claim.claim_type, str(claim.value).casefold())
            existing = unique.get(key)
            if existing is None:
                unique[key] = claim
                continue
            citations = [*existing.citations]
            citations.extend(item for item in claim.citations if item not in citations)
            unique[key] = existing.model_copy(update={"citations": citations})
        return list(unique.values())

    @staticmethod
    def _synthesize_components(
        claims: list[EvidenceClaim],
        component_names: dict[str, str],
    ) -> list[ComponentContext]:
        grouped: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        for claim in claims:
            if claim.status == "supported":
                grouped[claim.subject_key][claim.claim_type].append(str(claim.value))

        components: list[ComponentContext] = []
        for key, attributes in grouped.items():
            if key == "system" and key not in component_names:
                continue
            purposes = attributes.get("purpose", [])
            components.append(
                ComponentContext(
                    key=key,
                    display_name=component_names.get(key, key.replace("-", " ").title()),
                    purpose=purposes[0] if purposes else None,
                    capabilities=attributes.get("capability", []),
                    inputs=attributes.get("input", []),
                    outputs=attributes.get("output", []),
                    tools=attributes.get("tool", []),
                    dependencies=attributes.get("dependency", []),
                    policies=attributes.get("policy", []),
                )
            )
        return components
