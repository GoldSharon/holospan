from pathlib import Path

MIGRATION = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "20261123_0003_system_sources.py"
)


def test_ac5_ac6_source_migration_enforces_permissions_rls_and_indexes() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "system_context.sources.read" in sql
    assert "system_context.sources.manage" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "identity_current_tenant_id()" in sql
    assert "ix_system_context_source_tenant_system_created" in sql
    assert "GRANT SELECT, INSERT ON system_context_sources TO holospan_tenant_runtime" in sql
    assert "GRANT DELETE" not in sql
