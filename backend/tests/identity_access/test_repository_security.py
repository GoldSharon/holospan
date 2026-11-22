from typing import cast
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Executable

from holospan_api.domains.identity_access.models import PlatformRole, Principal, RecordStatus
from holospan_api.domains.identity_access.repository import IdentityRepository


class BootstrapRuntimeSession:
    """Model the auth runtime role, which can SELECT but cannot UPDATE role rows."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, statement: Executable) -> None:
        self.statements.append(str(statement))

    async def scalar(self, statement: Executable) -> object:
        rendered = str(statement)
        self.statements.append(rendered)
        if "identity_platform_roles" in rendered:
            if "FOR UPDATE" in rendered:
                raise PermissionError("permission denied for table identity_platform_roles")
            return PlatformRole(
                id=uuid4(),
                key="platform_admin",
                display_name="Platform administrator",
                is_system=True,
            )
        return 1


async def test_reveals_bug_bootstrap_does_not_require_role_table_update_privilege() -> None:
    runtime_session = BootstrapRuntimeSession()
    repository = IdentityRepository(cast(AsyncSession, runtime_session))
    principal = Principal(
        id=uuid4(),
        issuer="https://id.example",
        subject="bootstrap-admin",
        status=RecordStatus.ACTIVE,
    )

    assigned = await repository.bootstrap_platform_admin(
        principal=principal,
        request_id="bootstrap-test",
    )

    assert not assigned
    assert "pg_advisory_xact_lock" in runtime_session.statements[0]
    assert all("FOR UPDATE" not in statement for statement in runtime_session.statements)
