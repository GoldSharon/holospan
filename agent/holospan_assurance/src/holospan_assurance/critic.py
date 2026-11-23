from uuid import UUID

from holospan_assurance.contracts import ContextSnapshotCandidate, CriticResult


class ContextCritic:
    """Deterministic non-compensable gates for context publication."""

    def evaluate(
        self,
        snapshot: ContextSnapshotCandidate,
        *,
        allowed_source_ids: set[UUID],
    ) -> CriticResult:
        all_claims_cited = bool(snapshot.claims) and all(
            claim.citations
            and all(citation.source_id in allowed_source_ids for citation in claim.citations)
            for claim in snapshot.claims
        )
        supported_capabilities = {
            (claim.subject_key, str(claim.value))
            for claim in snapshot.claims
            if claim.status == "supported" and claim.claim_type == "capability"
        }
        no_invented_capabilities = all(
            (component.key, capability) in supported_capabilities
            for component in snapshot.components
            for capability in component.capabilities
        )
        gates = {
            "schema_valid": True,
            "tenant_attribution_valid": bool(snapshot.tenant_id and snapshot.system_id),
            "all_published_claims_cited": all_claims_cited,
            "no_invented_capabilities": no_invented_capabilities,
        }
        issues = [name for name, passed in gates.items() if not passed]
        score = sum(gates.values()) / len(gates)
        return CriticResult(
            score=score,
            passed=score >= 0.9 and not issues,
            gates=gates,
            issues=issues,
        )
