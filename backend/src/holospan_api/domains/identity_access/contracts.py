from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from typing_extensions import TypeForm


class OidcClientConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    enabled: bool
    authority: str | None = None
    client_id: str | None = Field(default=None, alias="clientId")
    scope: str | None = None
    redirect_uri: str | None = Field(default=None, alias="redirectUri")


class PrincipalSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: UUID
    email: str | None = None
    display_name: str | None = Field(default=None, alias="displayName")
    status: str


class MembershipSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    tenant_id: UUID = Field(alias="tenantId")
    tenant_slug: str = Field(alias="tenantSlug")
    tenant_name: str = Field(alias="tenantName")
    roles: list[str]
    permissions: list[str]
    status: str


class SessionContext(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    principal: PrincipalSummary
    memberships: list[MembershipSummary]
    platform_roles: list[str] = Field(alias="platformRoles")
    platform_permissions: list[str] = Field(alias="platformPermissions")
    selected_tenant_id: UUID | None = Field(default=None, alias="selectedTenantId")
    csrf_token: str = Field(alias="csrfToken")
    expires_at: datetime = Field(alias="expiresAt")


class LogoutResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    redirect_uri: str = Field(alias="redirectUri")


class InitialAdmin(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    issuer: HttpUrl
    subject: str = Field(min_length=1, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    display_name: str | None = Field(default=None, max_length=120, alias="displayName")


class CreateTenantRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    slug: str = Field(
        pattern=r"^[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])?$",
        min_length=3,
        max_length=63,
    )
    display_name: str = Field(min_length=1, max_length=120, alias="displayName")
    initial_admin: InitialAdmin = Field(alias="initialAdmin")


class TenantSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: UUID
    slug: str
    display_name: str = Field(alias="displayName")
    status: str
    created_at: datetime | None = Field(default=None, alias="createdAt")


class CursorPage[T](BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[T]
    next_cursor: str | None = Field(default=None, alias="nextCursor")

    @classmethod
    def model_parametrized_name(cls, params: tuple[TypeForm[Any], ...]) -> str:
        return f"{getattr(params[0], '__name__', 'Data')}CursorPage"


class MemberSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    membership_id: UUID = Field(alias="membershipId")
    principal: PrincipalSummary
    roles: list[str]
    permissions: list[str]
    status: str


class ReplaceMemberRolesRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    role_ids: list[UUID] = Field(alias="roleIds", max_length=20)

    @field_validator("role_ids")
    @classmethod
    def unique_roles(cls, role_ids: list[UUID]) -> list[UUID]:
        if len(role_ids) != len(set(role_ids)):
            raise ValueError("roleIds must be unique")
        return role_ids
