from uuid import uuid4

import pytest

from holospan_api.domains.identity_access.authorization import (
    Actor,
    AuthorizationDenied,
    Plane,
    require_permission,
)


def test_ac4_explicit_tenant_permission_allows_same_tenant() -> None:
    tenant_id = uuid4()
    actor = Actor(
        principal_id=uuid4(),
        plane=Plane.TENANT,
        tenant_permissions={tenant_id: frozenset({"tenant.members.read"})},
    )

    require_permission(actor, "tenant.members.read", tenant_id=tenant_id)


def test_ac3_permission_is_denied_for_another_tenant() -> None:
    actor = Actor(
        principal_id=uuid4(),
        plane=Plane.TENANT,
        tenant_permissions={uuid4(): frozenset({"tenant.members.read"})},
    )

    with pytest.raises(AuthorizationDenied):
        require_permission(actor, "tenant.members.read", tenant_id=uuid4())


def test_ac5_tenant_plane_never_satisfies_platform_permission() -> None:
    actor = Actor(
        principal_id=uuid4(),
        plane=Plane.TENANT,
        platform_permissions=frozenset({"platform.tenants.read"}),
    )

    with pytest.raises(AuthorizationDenied):
        require_permission(actor, "platform.tenants.read", plane=Plane.PLATFORM)


def test_deny_by_default_for_unknown_permission() -> None:
    actor = Actor(principal_id=uuid4(), plane=Plane.TENANT)

    with pytest.raises(AuthorizationDenied):
        require_permission(actor, "tenant.unknown")
