from holospan_api.domains.system_catalog.contracts import Capability


def current_capabilities() -> list[Capability]:
    """Return capabilities implemented by this exact backend release."""
    return [
        Capability(
            id="health",
            name="Operational health contract",
            status="available",
            description="Versioned liveness and PostgreSQL readiness probes.",
        ),
        Capability(
            id="context-ingestion",
            name="Context ingestion",
            status="planned",
            description="Code, requirements, media, API contracts, and trace context.",
        ),
        Capability(
            id="telemetry-ingestion",
            name="Telemetry ingestion",
            status="planned",
            description="OTLP, OpenInference, batch, and vendor trace ingestion.",
        ),
        Capability(
            id="assurance-runs",
            name="Assurance runs",
            status="planned",
            description="Scenario execution, evaluation, evidence, and decisions.",
        ),
    ]
