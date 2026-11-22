from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from holospan_api.domains.identity_access.models import RecordStatus, Tenant
from holospan_api.domains.identity_access.pagination import (
    CursorCodec,
    CursorPosition,
    InvalidCursor,
)
from holospan_api.domains.identity_access.repository import IdentityRepository


def test_ac17_cursor_is_opaque_tamper_evident_and_endpoint_scoped() -> None:
    codec = CursorCodec("test-pagination-secret-at-least-32-bytes")
    position = CursorPosition(
        created_at=datetime(2026, 11, 22, 12, 30, tzinfo=UTC),
        item_id=uuid4(),
    )

    encoded = codec.encode(position, scope="platform-tenants")

    assert str(position.item_id) not in encoded
    assert position.created_at.isoformat() not in encoded
    assert codec.decode(encoded, scope="platform-tenants") == position
    with pytest.raises(InvalidCursor):
        codec.decode(encoded, scope="tenant-members")
    with pytest.raises(InvalidCursor):
        codec.decode(encoded + "tampered", scope="platform-tenants")


async def test_ac17_platform_tenant_page_defaults_can_be_bounded_to_fifty() -> None:
    session = MagicMock()
    session.scalars = AsyncMock()
    created_at = datetime(2026, 11, 22, 12, 30, tzinfo=UTC)
    tenants = [
        Tenant(
            id=uuid4(),
            slug=f"tenant-{index:02d}",
            display_name=f"Tenant {index}",
            status=RecordStatus.ACTIVE,
            created_by=uuid4(),
            created_at=created_at,
        )
        for index in range(51)
    ]
    scalar_result = MagicMock()
    scalar_result.all.return_value = tenants
    session.scalars.return_value = scalar_result

    page = await IdentityRepository(session).list_platform_tenants(limit=50, after=None)

    assert len(page.items) == 50
    assert page.next_position == CursorPosition(
        created_at=created_at, item_id=tenants[49].id
    )


async def test_ac17_member_page_uses_two_queries_independent_of_page_size() -> None:
    session = MagicMock()
    session.execute = AsyncMock()
    tenant_id = uuid4()
    created_at = datetime(2026, 11, 22, 12, 30, tzinfo=UTC)
    member_rows = []
    access_rows = []
    for index in range(50):
        membership_id = uuid4()
        principal_id = uuid4()
        member_rows.append(
            (
                SimpleNamespace(
                    id=membership_id,
                    tenant_id=tenant_id,
                    principal_id=principal_id,
                    status=RecordStatus.ACTIVE,
                    created_at=created_at,
                ),
                SimpleNamespace(
                    id=principal_id,
                    email=f"member-{index}@example.test",
                    display_name=f"Member {index}",
                    status=RecordStatus.ACTIVE,
                ),
            )
        )
        access_rows.append((membership_id, "viewer", "tenant.read"))

    member_result = MagicMock()
    member_result.all.return_value = member_rows
    access_result = MagicMock()
    access_result.all.return_value = access_rows
    session.execute.side_effect = [member_result, access_result]

    page = await IdentityRepository(session).list_members(
        tenant_id, limit=50, after=None
    )

    assert len(page.items) == 50
    assert session.execute.await_count == 2
    assert page.items[0].roles == ["viewer"]
    assert page.items[0].permissions == ["tenant.read"]


async def test_ac17_member_page_fetches_one_extra_row_for_next_cursor() -> None:
    session = MagicMock()
    session.execute = AsyncMock()
    tenant_id = uuid4()
    created_at = datetime(2026, 11, 22, 12, 30, tzinfo=UTC)
    member_rows = []
    for index in range(3):
        principal_id = uuid4()
        member_rows.append(
            (
                SimpleNamespace(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    principal_id=principal_id,
                    status=RecordStatus.ACTIVE,
                    created_at=created_at,
                ),
                SimpleNamespace(
                    id=principal_id,
                    email=f"member-{index}@example.test",
                    display_name=f"Member {index}",
                    status=RecordStatus.ACTIVE,
                ),
            )
        )
    member_result = MagicMock()
    member_result.all.return_value = member_rows
    access_result = MagicMock()
    access_result.all.return_value = []
    session.execute.side_effect = [member_result, access_result]

    page = await IdentityRepository(session).list_members(
        tenant_id, limit=2, after=None
    )

    assert len(page.items) == 2
    assert page.next_position == CursorPosition(
        created_at=created_at, item_id=member_rows[1][0].id
    )
