import hashlib
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from holospan_api.domains.identity_access.errors import IdentityProblem
from holospan_api.domains.system_context.models import SourceKind, SourceRecord
from holospan_api.domains.system_context.service import SystemContextService
from holospan_api.domains.system_context.storage import ObjectStorageUnavailable

from .test_service import authenticated_request


def make_source_service() -> tuple[SystemContextService, MagicMock, MagicMock, MagicMock]:
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    identity = MagicMock()
    identity.authorize_tenant = AsyncMock()
    storage = MagicMock()
    storage.put_object = AsyncMock()
    storage.delete_object = AsyncMock()
    service = SystemContextService(
        session=session,
        identity_service=identity,
        object_storage=storage,
    )
    service.repository = MagicMock()
    service.repository.get_system = AsyncMock(return_value=MagicMock())
    return service, session, identity, storage


async def test_ac3_stores_exact_bytes_and_safe_attributed_metadata() -> None:
    service, session, identity, storage = make_source_service()
    tenant_id = uuid4()
    system_id = uuid4()
    authenticated = authenticated_request(tenant_id)
    now = datetime.now(UTC)

    async def create_source(**values: object) -> SourceRecord:
        actor = values.pop("actor")
        values.pop("request_id")
        return SourceRecord(
            **values,
            created_by=actor.principal_id,
            status="stored",
            created_at=now,
            updated_at=now,
        )

    service.repository.create_source = AsyncMock(side_effect=create_source)
    content = b"openapi: 3.1.0\ninfo:\n  title: Claims API\n"

    result = await service.create_source(
        authenticated=authenticated,
        tenant_id=tenant_id,
        system_id=system_id,
        kind=SourceKind.API_CONTRACT,
        original_filename="claims-api.yaml",
        declared_media_type="application/yaml",
        content=content,
        request_id="request-source-1",
    )

    identity.authorize_tenant.assert_awaited_once_with(
        authenticated,
        tenant_id,
        permission="system_context.sources.manage",
        request_id="request-source-1",
    )
    put = storage.put_object.await_args.kwargs
    assert put["data"] == content
    assert put["object_key"].endswith("/raw")
    assert "claims-api.yaml" not in put["object_key"]
    assert result.sha256 == hashlib.sha256(content).hexdigest()
    assert "object_key" not in result.model_dump()
    assert "storage_bucket" not in result.model_dump()
    session.commit.assert_awaited_once()


async def test_ac8_storage_failure_creates_no_row_or_success() -> None:
    service, session, _identity, storage = make_source_service()
    tenant_id = uuid4()
    storage.put_object.side_effect = ObjectStorageUnavailable()
    service.repository.create_source = AsyncMock()

    with pytest.raises(IdentityProblem) as problem:
        await service.create_source(
            authenticated=authenticated_request(tenant_id),
            tenant_id=tenant_id,
            system_id=uuid4(),
            kind=SourceKind.CONTEXT_DOCUMENT,
            original_filename="requirements.md",
            declared_media_type="text/markdown",
            content=b"# Requirements",
            request_id="request-source-2",
        )

    assert problem.value.code == "SOURCE_STORAGE_UNAVAILABLE"
    service.repository.create_source.assert_not_awaited()
    session.commit.assert_not_awaited()


async def test_ac9_database_failure_attempts_object_cleanup() -> None:
    service, session, _identity, storage = make_source_service()
    tenant_id = uuid4()
    service.repository.create_source = AsyncMock(side_effect=SQLAlchemyError("database failed"))

    with pytest.raises(IdentityProblem) as problem:
        await service.create_source(
            authenticated=authenticated_request(tenant_id),
            tenant_id=tenant_id,
            system_id=uuid4(),
            kind=SourceKind.CONTEXT_DOCUMENT,
            original_filename="requirements.md",
            declared_media_type="text/markdown",
            content=b"# Requirements",
            request_id="request-source-3",
        )

    assert problem.value.code == "SYSTEM_CONTEXT_UNAVAILABLE"
    session.rollback.assert_awaited_once()
    storage.delete_object.assert_awaited_once()


@pytest.mark.parametrize(
    ("filename", "content", "expected_code"),
    [
        ("empty.md", b"", "SOURCE_TYPE_UNSUPPORTED"),
        ("program.exe", b"not executable", "SOURCE_TYPE_UNSUPPORTED"),
        ("spoofed.md", b"safe-prefix\x00binary", "SOURCE_TYPE_UNSUPPORTED"),
        ("large.md", b"x" * (2 * 1024 * 1024 + 1), "SOURCE_TOO_LARGE"),
    ],
)
async def test_ac10_rejects_invalid_content_before_storage(
    filename: str,
    content: bytes,
    expected_code: str,
) -> None:
    service, session, _identity, storage = make_source_service()
    tenant_id = uuid4()

    with pytest.raises(IdentityProblem) as problem:
        await service.create_source(
            authenticated=authenticated_request(tenant_id),
            tenant_id=tenant_id,
            system_id=uuid4(),
            kind=SourceKind.CONTEXT_DOCUMENT,
            original_filename=filename,
            declared_media_type="text/plain",
            content=content,
            request_id="request-source-invalid",
        )

    assert problem.value.code == expected_code
    storage.put_object.assert_not_awaited()
    session.commit.assert_not_awaited()
