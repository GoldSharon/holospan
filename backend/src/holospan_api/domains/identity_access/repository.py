import hashlib
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from holospan_api.domains.identity_access.authorization import Actor, Plane
from holospan_api.domains.identity_access.contracts import (
    CreateTenantRequest,
    MembershipSummary,
    MemberSummary,
    PrincipalSummary,
    SessionContext,
    TenantSummary,
)
from holospan_api.domains.identity_access.models import (
    AuditOutcome,
    AuthorizationAuditOutbox,
    BrowserSession,
    Membership,
    MembershipRole,
    PlatformPermission,
    PlatformRole,
    PlatformRolePermission,
    Principal,
    PrincipalPlatformRole,
    RecordStatus,
    SessionPlane,
    Tenant,
    TenantPermission,
    TenantRole,
    TenantRolePermission,
)
from holospan_api.domains.identity_access.oidc import OidcIdentity
from holospan_api.domains.identity_access.pagination import CursorPosition, RepositoryPage


def token_digest(value: str) -> bytes:
    return hashlib.sha256(value.encode()).digest()


@dataclass(frozen=True, slots=True)
class IssuedSession:
    session_token: str
    csrf_token: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ResolvedIdentity:
    actor: Actor
    principal: Principal
    session: BrowserSession
    context: SessionContext


class IdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_principal(self, identity: OidcIdentity, *, now: datetime) -> Principal:
        statement = (
            postgresql_insert(Principal)
            .values(
                id=uuid4(),
                issuer=identity.issuer,
                subject=identity.subject,
                email=identity.email,
                display_name=identity.display_name,
                status=RecordStatus.ACTIVE,
                last_seen_at=now,
                version=1,
            )
            .on_conflict_do_update(
                constraint="uq_principal_issuer_subject",
                set_={
                    "email": identity.email,
                    "display_name": identity.display_name,
                    "last_seen_at": now,
                    "updated_at": now,
                    "version": Principal.version + 1,
                },
            )
            .returning(Principal.id)
        )
        principal_id = await self.session.scalar(statement)
        if principal_id is None:
            raise RuntimeError("principal upsert did not return an identifier")
        principal = await self.session.get(Principal, principal_id)
        if principal is None:
            raise RuntimeError("principal upsert result could not be loaded")
        return principal

    async def issue_session(
        self,
        *,
        principal: Principal,
        plane: Plane,
        auth_time: datetime,
        lifetime_seconds: int,
        now: datetime,
    ) -> IssuedSession:
        session_token = secrets.token_urlsafe(48)
        csrf_token = secrets.token_urlsafe(32)
        expires_at = now + timedelta(seconds=lifetime_seconds)
        self.session.add(
            BrowserSession(
                token_digest=token_digest(session_token),
                csrf_digest=token_digest(csrf_token),
                principal_id=principal.id,
                plane=SessionPlane(plane.value),
                auth_time=auth_time,
                last_seen_at=now,
                expires_at=expires_at,
            )
        )
        await self.session.flush()
        return IssuedSession(session_token, csrf_token, expires_at)

    async def resolve_session(
        self,
        *,
        session_token: str,
        csrf_token: str,
        plane: Plane,
        selected_tenant_id: UUID | None,
        now: datetime | None = None,
    ) -> ResolvedIdentity | None:
        current = now or datetime.now(UTC)
        row = (
            await self.session.execute(
                select(BrowserSession, Principal)
                .join(Principal, Principal.id == BrowserSession.principal_id)
                .where(
                    BrowserSession.token_digest == token_digest(session_token),
                    BrowserSession.csrf_digest == token_digest(csrf_token),
                    BrowserSession.plane == SessionPlane(plane.value),
                    BrowserSession.revoked_at.is_(None),
                    BrowserSession.expires_at > current,
                    Principal.status == RecordStatus.ACTIVE,
                )
            )
        ).one_or_none()
        if row is None:
            return None
        browser_session, principal = row
        browser_session.last_seen_at = current
        await self.session.execute(
            text("SELECT identity_activate_auth_context(:digest)"),
            {"digest": browser_session.token_digest},
        )

        memberships = (
            await self._membership_summaries(principal.id) if plane is Plane.TENANT else []
        )
        tenant_permissions = {
            item.tenant_id: frozenset(item.permissions)
            for item in memberships
            if item.status == RecordStatus.ACTIVE.value
        }
        platform_roles, platform_permissions = (
            await self._platform_access(principal.id)
            if plane is Plane.PLATFORM
            else ([], [])
        )
        actor = Actor(
            principal_id=principal.id,
            plane=plane,
            tenant_permissions=tenant_permissions,
            platform_permissions=frozenset(platform_permissions),
            session_id=browser_session.id,
            session_digest=browser_session.token_digest,
        )
        context = SessionContext.model_validate(
            {
                "principal": PrincipalSummary.model_validate(principal),
                "memberships": memberships,
                "platformRoles": platform_roles,
                "platformPermissions": platform_permissions,
                "selectedTenantId": selected_tenant_id,
                "csrfToken": csrf_token,
            }
        )
        return ResolvedIdentity(actor, principal, browser_session, context)

    async def activate_tenant_context(self, *, actor: Actor, tenant_id: UUID) -> None:
        if actor.session_digest is None:
            raise ValueError("validated session digest is required")
        await self.session.execute(
            text("SELECT identity_activate_tenant_context(:digest, :tenant_id)"),
            {"digest": actor.session_digest, "tenant_id": tenant_id},
        )

    async def _membership_summaries(self, principal_id: UUID) -> list[MembershipSummary]:
        rows = (
            await self.session.execute(
                select(Membership, Tenant)
                .join(Tenant, Tenant.id == Membership.tenant_id)
                .where(
                    Membership.principal_id == principal_id,
                    Membership.status == RecordStatus.ACTIVE,
                    Tenant.status == RecordStatus.ACTIVE,
                )
                .order_by(Tenant.display_name)
            )
        ).all()
        result: list[MembershipSummary] = []
        for membership, tenant in rows:
            role_rows = (
                await self.session.execute(
                    select(TenantRole.key, TenantPermission.key)
                    .select_from(MembershipRole)
                    .join(TenantRole, TenantRole.id == MembershipRole.role_id)
                    .outerjoin(TenantRolePermission, TenantRolePermission.role_id == TenantRole.id)
                    .outerjoin(
                        TenantPermission,
                        TenantPermission.key == TenantRolePermission.permission_key,
                    )
                    .where(MembershipRole.membership_id == membership.id)
                )
            ).all()
            result.append(
                MembershipSummary.model_validate(
                    {
                        "id": membership.id,
                        "tenantId": tenant.id,
                        "tenantSlug": tenant.slug,
                        "tenantName": tenant.display_name,
                        "roles": sorted({role for role, _ in role_rows}),
                        "permissions": sorted(
                            {permission for _, permission in role_rows if permission}
                        ),
                        "status": membership.status.value,
                    }
                )
            )
        return result

    async def _platform_access(self, principal_id: UUID) -> tuple[list[str], list[str]]:
        rows = (
            await self.session.execute(
                select(PlatformRole.key, PlatformPermission.key)
                .select_from(PrincipalPlatformRole)
                .join(PlatformRole, PlatformRole.id == PrincipalPlatformRole.role_id)
                .outerjoin(
                    PlatformRolePermission,
                    PlatformRolePermission.role_id == PlatformRole.id,
                )
                .outerjoin(
                    PlatformPermission,
                    PlatformPermission.key == PlatformRolePermission.permission_key,
                )
                .where(PrincipalPlatformRole.principal_id == principal_id)
            )
        ).all()
        return (
            sorted({role for role, _ in rows}),
            sorted({permission for _, permission in rows if permission}),
        )

    async def revoke_session(self, session_id: UUID, *, now: datetime) -> None:
        browser_session = await self.session.get(BrowserSession, session_id)
        if browser_session is not None:
            browser_session.revoked_at = now

    async def csrf_matches(self, session_id: UUID, csrf_token: str) -> bool:
        digest = await self.session.scalar(
            select(BrowserSession.csrf_digest).where(BrowserSession.id == session_id)
        )
        return digest is not None and secrets.compare_digest(digest, token_digest(csrf_token))

    async def delete_expired_sessions(self, *, now: datetime) -> int:
        result = await self.session.execute(
            delete(BrowserSession).where(BrowserSession.expires_at <= now)
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def active_tenant_admin_count(self, tenant_id: UUID) -> int:
        statement = (
            select(func.count(func.distinct(Membership.id)))
            .select_from(Membership)
            .join(MembershipRole, MembershipRole.membership_id == Membership.id)
            .join(TenantRole, TenantRole.id == MembershipRole.role_id)
            .where(
                Membership.tenant_id == tenant_id,
                Membership.status == RecordStatus.ACTIVE,
                TenantRole.key == "tenant_admin",
            )
        )
        return int(await self.session.scalar(statement) or 0)

    async def bootstrap_platform_admin(
        self,
        *,
        principal: Principal,
        request_id: str,
    ) -> bool:
        # Serialize the one-time bootstrap without row-locking the immutable role
        # catalog. SELECT FOR UPDATE would require UPDATE privileges that the
        # least-privileged authentication runtime intentionally does not hold.
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(-6706654064955872707)")
        )
        admin_role = await self.session.scalar(
            select(PlatformRole)
            .where(
                PlatformRole.key == "platform_admin",
                PlatformRole.is_system.is_(True),
            )
        )
        if admin_role is None:
            raise RuntimeError("platform_admin role is not seeded")
        existing_count = int(
            await self.session.scalar(select(func.count()).select_from(PrincipalPlatformRole)) or 0
        )
        if existing_count > 0:
            return False
        self.session.add(PrincipalPlatformRole(principal_id=principal.id, role_id=admin_role.id))
        self.session.add(
            AuthorizationAuditOutbox(
                stream="platform",
                actor_principal_id=principal.id,
                action="platform.bootstrap.assign",
                target_type="principal",
                target_id=str(principal.id),
                outcome=AuditOutcome.SUCCEEDED,
                reason_code="BOOTSTRAP_PLATFORM_ADMIN_ASSIGNED",
                request_id=request_id,
                principal_type="human",
                session_type="platform",
                policy_version="identity-access-v1",
                event_metadata={},
                occurred_at=datetime.now(UTC),
            )
        )
        await self.session.flush()
        return True

    async def record_authorization_denial(
        self,
        *,
        actor: Actor,
        action: str,
        tenant_id: UUID | None,
        request_id: str,
    ) -> None:
        safe_tenant_id = (
            tenant_id if tenant_id is not None and tenant_id in actor.tenant_permissions else None
        )
        self.session.add(
            AuthorizationAuditOutbox(
                stream=actor.plane.value,
                tenant_id=safe_tenant_id,
                actor_principal_id=actor.principal_id,
                action=action,
                outcome=AuditOutcome.DENIED,
                reason_code="PERMISSION_DENIED",
                request_id=request_id,
                principal_type="human",
                session_type=actor.plane.value,
                policy_version="identity-access-v1",
                event_metadata={"requestedTenantScoped": tenant_id is not None},
                occurred_at=datetime.now(UTC),
            )
        )
        await self.session.flush()

    async def record_anonymous_denial(self, *, action: str, request_id: str) -> None:
        self.session.add(
            AuthorizationAuditOutbox(
                stream="platform",
                action=action,
                outcome=AuditOutcome.DENIED,
                reason_code="PERMISSION_DENIED",
                request_id=request_id,
                principal_type="anonymous",
                session_type="none",
                policy_version="identity-access-v1",
                event_metadata={},
                occurred_at=datetime.now(UTC),
            )
        )
        await self.session.flush()

    async def list_membership_tenants(
        self,
        principal_id: UUID,
        *,
        limit: int,
        after: CursorPosition | None,
    ) -> RepositoryPage[TenantSummary]:
        statement = (
            select(Tenant)
            .join(Membership, Membership.tenant_id == Tenant.id)
            .where(
                Membership.principal_id == principal_id,
                Membership.status == RecordStatus.ACTIVE,
                Tenant.status == RecordStatus.ACTIVE,
            )
            .order_by(Tenant.created_at, Tenant.id)
            .limit(limit + 1)
        )
        if after is not None:
            statement = statement.where(
                or_(
                    Tenant.created_at > after.created_at,
                    and_(
                        Tenant.created_at == after.created_at,
                        Tenant.id > after.item_id,
                    ),
                )
            )
        tenants = list((await self.session.scalars(statement)).all())
        has_more = len(tenants) > limit
        tenants = tenants[:limit]
        return RepositoryPage(
            items=[TenantSummary.model_validate(tenant) for tenant in tenants],
            next_position=(
                CursorPosition(tenants[-1].created_at, tenants[-1].id)
                if has_more and tenants
                else None
            ),
        )

    async def list_platform_tenants(
        self, *, limit: int, after: CursorPosition | None
    ) -> RepositoryPage[TenantSummary]:
        statement = select(Tenant).order_by(Tenant.created_at, Tenant.id).limit(limit + 1)
        if after is not None:
            statement = statement.where(
                or_(
                    Tenant.created_at > after.created_at,
                    and_(
                        Tenant.created_at == after.created_at,
                        Tenant.id > after.item_id,
                    ),
                )
            )
        tenants = list((await self.session.scalars(statement)).all())
        has_more = len(tenants) > limit
        tenants = tenants[:limit]
        return RepositoryPage(
            items=[TenantSummary.model_validate(tenant) for tenant in tenants],
            next_position=(
                CursorPosition(tenants[-1].created_at, tenants[-1].id)
                if has_more and tenants
                else None
            ),
        )

    async def create_tenant_with_initial_admin(
        self,
        *,
        request: CreateTenantRequest,
        actor: Actor,
        request_id: str,
        now: datetime,
    ) -> TenantSummary:
        initial = request.initial_admin
        principal = await self.upsert_principal(
            OidcIdentity(
                issuer=str(initial.issuer).rstrip("/"),
                subject=initial.subject,
                email=initial.email,
                display_name=initial.display_name,
                auth_time=now,
            ),
            now=now,
        )
        tenant = Tenant(
            slug=request.slug,
            display_name=request.display_name,
            status=RecordStatus.ACTIVE,
            created_by=actor.principal_id,
        )
        self.session.add(tenant)
        await self.session.flush()
        membership = Membership(
            tenant_id=tenant.id,
            principal_id=principal.id,
            status=RecordStatus.ACTIVE,
        )
        self.session.add(membership)
        await self.session.flush()
        admin_role_id = await self.session.scalar(
            select(TenantRole.id).where(
                TenantRole.key == "tenant_admin",
                TenantRole.tenant_id.is_(None),
                TenantRole.is_system.is_(True),
            )
        )
        if admin_role_id is None:
            raise RuntimeError("tenant_admin role is not seeded")
        self.session.add(
            MembershipRole(
                membership_id=membership.id,
                tenant_id=tenant.id,
                role_id=admin_role_id,
            )
        )
        self.session.add(
            AuthorizationAuditOutbox(
                stream="platform",
                tenant_id=tenant.id,
                actor_principal_id=actor.principal_id,
                action="platform.tenant.create",
                target_type="tenant",
                target_id=str(tenant.id),
                outcome=AuditOutcome.SUCCEEDED,
                reason_code="TENANT_CREATED",
                request_id=request_id,
                principal_type="human",
                session_type="platform",
                policy_version="identity-access-v1",
                event_metadata={"tenantSlug": tenant.slug},
                occurred_at=datetime.now(UTC),
            )
        )
        await self.session.flush()
        return TenantSummary.model_validate(tenant)

    async def list_members(
        self,
        tenant_id: UUID,
        *,
        limit: int,
        after: CursorPosition | None,
    ) -> RepositoryPage[MemberSummary]:
        statement = (
            select(Membership, Principal)
            .join(Principal, Principal.id == Membership.principal_id)
            .where(Membership.tenant_id == tenant_id)
            .order_by(Membership.created_at, Membership.id)
            .limit(limit + 1)
        )
        if after is not None:
            statement = statement.where(
                or_(
                    Membership.created_at > after.created_at,
                    and_(
                        Membership.created_at == after.created_at,
                        Membership.id > after.item_id,
                    ),
                )
            )
        rows = list((await self.session.execute(statement)).all())
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = await self._hydrate_members(rows)
        return RepositoryPage(
            items=items,
            next_position=(
                CursorPosition(rows[-1][0].created_at, rows[-1][0].id)
                if has_more and rows
                else None
            ),
        )

    async def _hydrate_members(
        self, rows: Sequence[tuple[Membership, Principal]]
    ) -> list[MemberSummary]:
        if not rows:
            return []
        membership_ids = [membership.id for membership, _ in rows]
        access_rows = (
            await self.session.execute(
                select(MembershipRole.membership_id, TenantRole.key, TenantPermission.key)
                .select_from(MembershipRole)
                .join(TenantRole, TenantRole.id == MembershipRole.role_id)
                .outerjoin(TenantRolePermission, TenantRolePermission.role_id == TenantRole.id)
                .outerjoin(
                    TenantPermission,
                    TenantPermission.key == TenantRolePermission.permission_key,
                )
                .where(MembershipRole.membership_id.in_(membership_ids))
            )
        ).all()
        roles_by_member: dict[UUID, set[str]] = {value: set() for value in membership_ids}
        permissions_by_member: dict[UUID, set[str]] = {
            value: set() for value in membership_ids
        }
        for membership_id, role, permission in access_rows:
            roles_by_member[membership_id].add(role)
            if permission:
                permissions_by_member[membership_id].add(permission)
        result: list[MemberSummary] = []
        for membership, principal in rows:
            result.append(
                MemberSummary.model_validate(
                    {
                        "membershipId": membership.id,
                        "principal": PrincipalSummary.model_validate(principal),
                        "roles": sorted(roles_by_member[membership.id]),
                        "permissions": sorted(permissions_by_member[membership.id]),
                        "status": membership.status.value,
                    }
                )
            )
        return result

    async def get_member(self, tenant_id: UUID, membership_id: UUID) -> MemberSummary | None:
        row = (
            await self.session.execute(
                select(Membership, Principal)
                .join(Principal, Principal.id == Membership.principal_id)
                .where(Membership.id == membership_id, Membership.tenant_id == tenant_id)
            )
        ).one_or_none()
        if row is None:
            return None
        return (await self._hydrate_members([row]))[0]

    async def replace_member_roles(
        self,
        *,
        tenant_id: UUID,
        membership_id: UUID,
        role_ids: list[UUID],
        actor: Actor,
        request_id: str,
    ) -> MemberSummary | None:
        await self.session.execute(
            select(Tenant.id).where(Tenant.id == tenant_id).with_for_update()
        )
        membership = await self.session.scalar(
            select(Membership)
            .where(Membership.id == membership_id, Membership.tenant_id == tenant_id)
            .with_for_update()
        )
        if membership is None:
            return None
        roles = (
            await self.session.scalars(
                select(TenantRole).where(
                    TenantRole.id.in_(role_ids),
                    (TenantRole.tenant_id.is_(None) | (TenantRole.tenant_id == tenant_id)),
                )
            )
        ).all()
        if len(roles) != len(role_ids):
            return None
        existing = (
            await self.session.scalars(
                select(TenantRole)
                .join(MembershipRole, MembershipRole.role_id == TenantRole.id)
                .where(MembershipRole.membership_id == membership_id)
            )
        ).all()
        removing_admin = any(role.key == "tenant_admin" for role in existing) and not any(
            role.key == "tenant_admin" for role in roles
        )
        if removing_admin and await self.active_tenant_admin_count(tenant_id) <= 1:
            raise ValueError("LAST_TENANT_ADMIN_REQUIRED")
        await self.session.execute(
            delete(MembershipRole).where(MembershipRole.membership_id == membership_id)
        )
        self.session.add_all(
            [
                MembershipRole(
                    membership_id=membership_id,
                    tenant_id=tenant_id,
                    role_id=role.id,
                )
                for role in roles
            ]
        )
        before = token_digest("|".join(sorted(str(role.id) for role in existing)))
        after = token_digest("|".join(sorted(str(role.id) for role in roles)))
        self.session.add(
            AuthorizationAuditOutbox(
                stream="tenant",
                tenant_id=tenant_id,
                actor_principal_id=actor.principal_id,
                action="tenant.member.roles.replace",
                target_type="membership",
                target_id=str(membership_id),
                outcome=AuditOutcome.SUCCEEDED,
                reason_code="MEMBER_ROLES_REPLACED",
                request_id=request_id,
                principal_type="human",
                session_type="tenant",
                policy_version="identity-access-v1",
                before_digest=before,
                after_digest=after,
                event_metadata={"roleCount": len(roles)},
                occurred_at=datetime.now(UTC),
            )
        )
        await self.session.flush()
        return await self.get_member(tenant_id, membership_id)
