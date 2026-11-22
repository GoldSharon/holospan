from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID


class Plane(StrEnum):
    TENANT = "tenant"
    PLATFORM = "platform"


class AuthorizationDenied(Exception):
    """Raised when a deny-by-default policy decision does not permit an action."""


@dataclass(frozen=True, slots=True)
class Actor:
    principal_id: UUID
    plane: Plane
    tenant_permissions: dict[UUID, frozenset[str]] = field(default_factory=dict)
    platform_permissions: frozenset[str] = frozenset()
    session_id: UUID | None = None
    session_digest: bytes | None = None


def require_permission(
    actor: Actor,
    permission: str,
    *,
    tenant_id: UUID | None = None,
    plane: Plane | None = None,
) -> None:
    required_plane = plane or (Plane.TENANT if tenant_id is not None else actor.plane)
    if actor.plane is not required_plane:
        raise AuthorizationDenied

    if required_plane is Plane.PLATFORM:
        if permission not in actor.platform_permissions:
            raise AuthorizationDenied
        return

    if tenant_id is None or permission not in actor.tenant_permissions.get(tenant_id, frozenset()):
        raise AuthorizationDenied
