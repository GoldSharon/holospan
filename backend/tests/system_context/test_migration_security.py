from pathlib import Path

MIGRATION = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "20261122_0002_system_context.py"
)


def test_ac5_ac6_migration_enforces_rbac_rls_and_least_privilege() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "system_context.systems.read" in sql
    assert "system_context.systems.manage" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "identity_current_tenant_id()" in sql
    assert "GRANT SELECT, INSERT ON system_context_systems TO holospan_tenant_runtime" in sql
    assert "GRANT DELETE" not in sql
