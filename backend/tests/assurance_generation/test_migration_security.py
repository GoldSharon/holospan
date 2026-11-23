from pathlib import Path


def test_phase1_migration_enforces_permissions_rls_and_provenance() -> None:
    migration = Path("alembic/versions/20261123_0004_assurance_discovery.py")
    sql = migration.read_text()

    assert "assurance_generation.context.read" in sql
    assert "assurance_generation.context.generate" in sql
    assert "assurance_generation.context.review" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "assurance_artifact_citations" in sql
    assert "content_sha256" in sql
    assert "idempotency_key" in sql
