from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from holospan_api.core.config import Settings
from holospan_api.domains.identity_access.authorization import (
    Actor,
    AuthorizationDenied,
    Plane,
    require_permission,
)
from holospan_api.domains.identity_access.bootstrap import BootstrapAllowlist
from holospan_api.domains.identity_access.contracts import (
    CreateTenantRequest,
    CursorPage,
    MemberSummary,
    OidcClientConfig,
    SessionContext,
    TenantSummary,
)
from holospan_api.domains.identity_access.errors import (
    IdentityProblem,
    authentication_required,
    identity_not_configured,
    permission_denied,
)
from holospan_api.domains.identity_access.oidc import (
    AuthenticationFailed,
    LoginTransaction,
    LoginTransactionCodec,
    OidcProvider,
    build_authorization_url,
)
from holospan_api.domains.identity_access.pagination import (
    CursorCodec,
    CursorPosition,
    InvalidCursor,
    RepositoryPage,
)
from holospan_api.domains.identity_access.repository import IdentityRepository, IssuedSession


@dataclass(frozen=True, slots=True)
class PlaneConfiguration:
    enabled: bool
    issuer: str | None
    client_id: str | None
    redirect_uri: str
    frontend_uri: str
    scope: str


@dataclass(frozen=True, slots=True)
class AuthenticatedRequest:
    actor: Actor
    context: SessionContext


class IdentityService:
    def __init__(
        self,
        *,
        settings: Settings,
        session: AsyncSession,
        tenant_session: AsyncSession,
        tenant_provider: OidcProvider | None,
        platform_provider: OidcProvider | None,
    ) -> None:
        self.settings = settings
        self.repository = IdentityRepository(session)
        self.tenant_repository = IdentityRepository(tenant_session)
        self.session = session
        self.tenant_session = tenant_session
        self.providers = {
            Plane.TENANT: tenant_provider,
            Plane.PLATFORM: platform_provider,
        }
        self.codec = LoginTransactionCodec(settings.identity_session_secret.get_secret_value())
        self.cursor_codec = CursorCodec(settings.identity_session_secret.get_secret_value())

    def configuration(self, plane: Plane) -> PlaneConfiguration:
        if plane is Plane.PLATFORM:
            return PlaneConfiguration(
                enabled=self.settings.platform_oidc_enabled,
                issuer=self.settings.platform_oidc_issuer,
                client_id=self.settings.platform_oidc_client_id,
                redirect_uri=self.settings.platform_oidc_redirect_uri,
                frontend_uri=self.settings.platform_oidc_frontend_uri,
                scope=self.settings.oidc_scope,
            )
        return PlaneConfiguration(
            enabled=self.settings.oidc_enabled,
            issuer=self.settings.oidc_issuer,
            client_id=self.settings.oidc_client_id,
            redirect_uri=self.settings.oidc_redirect_uri,
            frontend_uri=self.settings.oidc_frontend_uri,
            scope=self.settings.oidc_scope,
        )

    def public_config(self, plane: Plane) -> OidcClientConfig:
        config = self.configuration(plane)
        if not config.enabled:
            return OidcClientConfig(enabled=False)
        return OidcClientConfig(
            enabled=True,
            authority=config.issuer,
            clientId=config.client_id,
            scope=config.scope,
            redirectUri=config.redirect_uri,
        )

    async def begin_login(self, plane: Plane) -> tuple[str, str]:
        config = self.configuration(plane)
        provider = self.providers[plane]
        if not config.enabled or provider is None or config.client_id is None:
            raise identity_not_configured()
        transaction = LoginTransaction.create()
        try:
            endpoint = await provider.authorization_endpoint()
        except AuthenticationFailed as exc:
            raise IdentityProblem(
                503,
                "IDENTITY_PROVIDER_UNAVAILABLE",
                "The identity provider is temporarily unavailable.",
            ) from exc
        return (
            build_authorization_url(
                authorization_endpoint=endpoint,
                client_id=config.client_id,
                redirect_uri=config.redirect_uri,
                scope=config.scope,
                transaction=transaction,
            ),
            self.codec.encode(transaction),
        )

    async def complete_login(
        self,
        *,
        plane: Plane,
        code: str,
        state: str,
        transaction_cookie: str | None,
        request_id: str,
    ) -> IssuedSession:
        config = self.configuration(plane)
        provider = self.providers[plane]
        if not config.enabled or provider is None:
            raise identity_not_configured()
        if not transaction_cookie:
            raise authentication_required()
        try:
            transaction = self.codec.decode(transaction_cookie)
            if transaction.state != state:
                raise AuthenticationFailed
            identity = await provider.exchange_code(
                code=code,
                redirect_uri=config.redirect_uri,
                transaction=transaction,
            )
        except AuthenticationFailed as exc:
            raise authentication_required() from exc
        now = datetime.now(UTC)
        principal = await self.repository.upsert_principal(identity, now=now)
        if plane is Plane.PLATFORM and BootstrapAllowlist.parse(
            self.settings.bootstrap_platform_admins
        ).matches(identity.issuer, identity.subject):
            await self.repository.bootstrap_platform_admin(
                principal=principal,
                request_id=request_id,
            )
        issued = await self.repository.issue_session(
            principal=principal,
            plane=plane,
            auth_time=identity.auth_time,
            lifetime_seconds=self.settings.identity_session_seconds,
            now=now,
        )
        await self.session.commit()
        return issued

    async def authenticate(
        self,
        *,
        plane: Plane,
        session_token: str | None,
        csrf_token: str | None,
        selected_tenant_id: UUID | None,
        request_id: str,
    ) -> AuthenticatedRequest:
        if not self.configuration(plane).enabled:
            raise identity_not_configured()
        if not session_token or not csrf_token:
            raise authentication_required()
        resolved = await self.repository.resolve_session(
            session_token=session_token,
            csrf_token=csrf_token,
            plane=plane,
            selected_tenant_id=selected_tenant_id,
        )
        if resolved is None:
            raise authentication_required()
        if (
            selected_tenant_id is not None
            and selected_tenant_id not in resolved.actor.tenant_permissions
        ):
            await self.repository.record_authorization_denial(
                actor=resolved.actor,
                action="tenant.context.select",
                tenant_id=selected_tenant_id,
                request_id=request_id,
            )
            await self.session.commit()
            raise permission_denied()
        return AuthenticatedRequest(resolved.actor, resolved.context)

    async def verify_csrf(
        self, request: AuthenticatedRequest, value: str | None, *, request_id: str
    ) -> None:
        if not value or request.actor.session_id is None:
            await self._audit_denial(request.actor, "session.csrf.verify", None, request_id)
            raise permission_denied()
        if not await self.repository.csrf_matches(request.actor.session_id, value):
            await self._audit_denial(request.actor, "session.csrf.verify", None, request_id)
            raise permission_denied()

    async def require_selected_tenant(
        self,
        request: AuthenticatedRequest,
        tenant_id: UUID,
        *,
        request_id: str,
    ) -> None:
        if request.context.selected_tenant_id != tenant_id:
            await self._audit_denial(
                request.actor, "tenant.context.match", tenant_id, request_id
            )
            raise permission_denied()

    async def authorize_tenant(
        self,
        request: AuthenticatedRequest,
        tenant_id: UUID,
        *,
        permission: str,
        request_id: str,
    ) -> None:
        """Authorize and activate a signed RLS context for a tenant-domain operation."""
        await self.require_selected_tenant(request, tenant_id, request_id=request_id)
        await self._require(
            request.actor,
            permission,
            tenant_id=tenant_id,
            request_id=request_id,
        )
        await self.tenant_repository.activate_tenant_context(
            actor=request.actor,
            tenant_id=tenant_id,
        )

    async def logout(self, request: AuthenticatedRequest) -> None:
        if request.actor.session_id is not None:
            await self.repository.revoke_session(request.actor.session_id, now=datetime.now(UTC))
            await self.session.commit()

    async def list_membership_tenants(
        self,
        request: AuthenticatedRequest,
        *,
        limit: int,
        cursor: str | None,
    ) -> CursorPage[TenantSummary]:
        scope = f"membership-tenants:{request.actor.principal_id}"
        page = await self.repository.list_membership_tenants(
            request.actor.principal_id,
            limit=limit,
            after=self._decode_cursor(cursor, scope=scope),
        )
        return self._encode_page(page, scope=scope)

    async def list_platform_tenants(
        self,
        request: AuthenticatedRequest,
        *,
        limit: int,
        cursor: str | None,
        request_id: str,
    ) -> CursorPage[TenantSummary]:
        await self._require(
            request.actor,
            "platform.tenants.read",
            plane=Plane.PLATFORM,
            request_id=request_id,
        )
        scope = "platform-tenants"
        page = await self.repository.list_platform_tenants(
            limit=limit,
            after=self._decode_cursor(cursor, scope=scope),
        )
        return self._encode_page(page, scope=scope)

    async def create_tenant(
        self,
        *,
        authenticated: AuthenticatedRequest,
        request: CreateTenantRequest,
        request_id: str,
    ) -> TenantSummary:
        await self._require(
            authenticated.actor,
            "platform.tenants.manage",
            plane=Plane.PLATFORM,
            request_id=request_id,
        )
        configured_issuer = (self.settings.oidc_issuer or "").rstrip("/")
        requested_issuer = str(request.initial_admin.issuer).rstrip("/")
        if not configured_issuer or requested_issuer != configured_issuer:
            await self._audit_denial(
                authenticated.actor,
                "platform.tenant.initial-admin.assign",
                None,
                request_id,
            )
            raise IdentityProblem(
                422,
                "INITIAL_ADMIN_ISSUER_INVALID",
                "The initial administrator must use the configured tenant issuer.",
            )
        try:
            result = await self.repository.create_tenant_with_initial_admin(
                request=request,
                actor=authenticated.actor,
                request_id=request_id,
                now=datetime.now(UTC),
            )
            await self.session.commit()
            return result
        except IntegrityError as exc:
            await self.session.rollback()
            raise IdentityProblem(
                409,
                "TENANT_SLUG_CONFLICT",
                "A tenant with that slug already exists.",
            ) from exc

    async def list_tenant_members(
        self,
        *,
        authenticated: AuthenticatedRequest,
        tenant_id: UUID,
        limit: int,
        cursor: str | None,
        request_id: str,
    ) -> CursorPage[MemberSummary]:
        await self._require(
            authenticated.actor,
            "tenant.members.read",
            tenant_id=tenant_id,
            request_id=request_id,
        )
        await self.tenant_repository.activate_tenant_context(
            actor=authenticated.actor, tenant_id=tenant_id
        )
        scope = f"tenant-members:{tenant_id}"
        page = await self.tenant_repository.list_members(
            tenant_id,
            limit=limit,
            after=self._decode_cursor(cursor, scope=scope),
        )
        return self._encode_page(page, scope=scope)

    def _decode_cursor(self, cursor: str | None, *, scope: str) -> CursorPosition | None:
        if cursor is None:
            return None
        try:
            return self.cursor_codec.decode(cursor, scope=scope)
        except InvalidCursor as exc:
            raise IdentityProblem(
                422,
                "INVALID_CURSOR",
                "The pagination cursor is invalid or is for another resource.",
            ) from exc

    def _encode_page[T](
        self, page: RepositoryPage[T], *, scope: str
    ) -> CursorPage[T]:
        return CursorPage(
            items=page.items,
            nextCursor=(
                self.cursor_codec.encode(page.next_position, scope=scope)
                if page.next_position is not None
                else None
            ),
        )

    async def replace_member_roles(
        self,
        *,
        authenticated: AuthenticatedRequest,
        tenant_id: UUID,
        membership_id: UUID,
        role_ids: list[UUID],
        request_id: str,
    ) -> MemberSummary:
        await self._require(
            authenticated.actor,
            "tenant.members.manage",
            tenant_id=tenant_id,
            request_id=request_id,
        )
        try:
            await self.tenant_repository.activate_tenant_context(
                actor=authenticated.actor, tenant_id=tenant_id
            )
            result = await self.tenant_repository.replace_member_roles(
                tenant_id=tenant_id,
                membership_id=membership_id,
                role_ids=role_ids,
                actor=authenticated.actor,
                request_id=request_id,
            )
            if result is None:
                await self.tenant_session.rollback()
                await self._audit_denial(
                    authenticated.actor,
                    "tenant.member.roles.replace",
                    tenant_id,
                    request_id,
                )
                raise permission_denied()
            await self.tenant_session.commit()
            return result
        except ValueError as exc:
            await self.tenant_session.rollback()
            if str(exc) == "LAST_TENANT_ADMIN_REQUIRED":
                raise IdentityProblem(
                    409,
                    "LAST_TENANT_ADMIN_REQUIRED",
                    "Every tenant must retain an active tenant administrator.",
                ) from exc
            raise

    async def audit_denial(
        self,
        *,
        actor: Actor | None,
        action: str,
        tenant_id: UUID | None,
        request_id: str,
    ) -> None:
        if actor is None:
            await self.repository.record_anonymous_denial(
                action=action, request_id=request_id
            )
            await self.session.commit()
            return
        await self._audit_denial(actor, action, tenant_id, request_id)

    async def _audit_denial(
        self,
        actor: Actor,
        action: str,
        tenant_id: UUID | None,
        request_id: str,
    ) -> None:
        await self.repository.record_authorization_denial(
            actor=actor,
            action=action,
            tenant_id=tenant_id,
            request_id=request_id,
        )
        await self.session.commit()

    async def _require(
        self,
        actor: Actor,
        permission: str,
        *,
        tenant_id: UUID | None = None,
        plane: Plane | None = None,
        request_id: str,
    ) -> None:
        try:
            require_permission(actor, permission, tenant_id=tenant_id, plane=plane)
        except AuthorizationDenied as exc:
            await self.repository.record_authorization_denial(
                actor=actor,
                action=permission,
                tenant_id=tenant_id,
                request_id=request_id,
            )
            await self.session.commit()
            raise permission_denied() from exc
