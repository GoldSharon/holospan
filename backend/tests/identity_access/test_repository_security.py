from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Executable

from holospan_api.domains.identity_access.authorization import Plane
from holospan_api.domains.identity_access.models import (
    BrowserSession,
    PlatformRole,
    Principal,
    RecordStatus,
    SessionPlane,
)
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


class ExpiredSessionRuntime:
    def __init__(self, browser_session: BrowserSession) -> None:
        self.browser_session = browser_session
        self.statement = ""

    async def scalar(self, statement: Executable) -> object:
        self.statement = str(statement)
        return self.browser_session


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


async def test_logout_can_revoke_a_session_after_its_absolute_expiry() -> None:
    now = datetime(2026, 11, 23, tzinfo=UTC)
    browser_session = BrowserSession(
        id=uuid4(),
        token_digest=b"expired-token-digest",
        csrf_digest=b"expired-csrf-digest",
        principal_id=uuid4(),
        plane=SessionPlane.TENANT,
        auth_time=now - timedelta(hours=2),
        last_seen_at=now - timedelta(hours=1),
        expires_at=now - timedelta(seconds=1),
    )
    runtime_session = ExpiredSessionRuntime(browser_session)
    repository = IdentityRepository(cast(AsyncSession, runtime_session))

    revoked = await repository.revoke_session_token(
        session_token="expired-session",  # noqa: S106
        plane=Plane.TENANT,
        now=now,
    )

    assert revoked
    assert browser_session.revoked_at == now
    assert "expires_at" not in runtime_session.statement.split("WHERE", 1)[1]
