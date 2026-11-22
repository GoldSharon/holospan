# Spec: Identity, Tenancy, and Access Control

**Author:** Codex with Gold Sharon
**Date:** 2026-11-22
**Status:** Approved
**Reviewers:** Gold Sharon (approval given by the instruction to start this slice)
**Related specs:** `docs/architecture/04_SECURITY_RBAC_THREAT_MODEL.md`

## Context

Holospan currently exposes a runnable application shell without an identity or
tenant boundary. The platform will hold customer requirements, traces,
evaluation evidence, findings, and administrative settings, including data
that may contain PII or confidential system behavior. No assurance feature can
be safely added until every request has a verified principal, tenant context,
and explicit permission decision.

The first deployment is a single EC2 Docker installation, but the identity
contract must remain portable to SaaS and customer-hosted AWS deployments.
Customers will bring different OpenID Connect (OIDC) providers, so Holospan
must validate standards-based access tokens without storing passwords. The
first slice provides a provider-neutral OIDC boundary, just-in-time principal
registration, tenant membership, system roles and permissions, and separate
tenant-administrator and platform-administrator scopes.

## Functional Requirements

- FR-1: The backend-for-frontend (BFF) MUST validate the signature, issuer,
  client audience, expiry, issued-at time, nonce, authorized party when present,
  token type, and algorithm of the OIDC ID token returned by the configured
  authorization-code with PKCE flow.
- FR-2: Protected browser routes MUST accept only an opaque Holospan session
  cookie; they MUST NOT accept an OIDC ID token as an API bearer token.
- FR-3: The system MUST create or update a local principal from the verified
  `(issuer, subject)` identity without storing an identity-provider password or token.
- FR-4: A principal MUST have an active tenant membership before tenant-scoped
  data can be returned or changed.
- FR-5: Authorization MUST be deny-by-default and MUST require an explicit
  permission granted by an active role assignment.
- FR-6: Tenant roles MUST be scoped independently from platform roles; a tenant
  administrator MUST NOT gain platform-administrator permissions.
- FR-7: A tenant administrator MUST be able to list tenant members and replace
  a member's tenant-role assignments within their tenant.
- FR-8: A platform administrator MUST be able to create a tenant with an initial
  tenant administrator and list all tenants through the platform-administration
  API; ordinary principals MAY list only active memberships through the tenant API.
- FR-9: Role replacement MUST reject platform roles, roles owned by another
  tenant, unknown roles, and removal of the final active tenant administrator.
- FR-10: Every tenant creation, membership-role change, bootstrap assignment,
  and authorization denial MUST create a structured audit outbox event without
  token, credential, cookie, or raw authorization-header data.
- FR-11: The session endpoint MUST return the authenticated principal, active
  memberships, effective permissions, platform roles, and selected tenant.
- FR-12: A configured bootstrap allowlist MAY grant the platform-administrator
  role only when both the verified issuer and subject exactly match an entry.
- FR-13: Existing application capability endpoints MUST become protected; only
  liveness, readiness, OpenAPI when enabled, and OIDC login/callback/configuration
  endpoints MAY remain anonymous.
- FR-14: The web application MUST present an OIDC authorization-code with PKCE
  sign-in action and MUST show a workspace selector after authentication.
- FR-15: Tenant administration and platform administration MUST use distinct
  routes, session cookies, configured hosts, OIDC client audiences, and audit streams.
- FR-16: State-changing browser requests MUST present a session-bound CSRF token
  in addition to the opaque session cookie.
- FR-17: Tenant and member list endpoints MUST use stable cursor pagination with
  a default page size of 50 and a hard maximum of 100.

## Non-Functional Requirements

- NFR-P1: With cached OIDC metadata and keys, token validation plus authorization
  MUST complete within 300 ms at p95 at 50 requests/second on the validation EC2 host.
- NFR-P2: Membership and permission lookups MUST use tenant-leading or
  principal-leading indexes and MUST NOT require full scans of tables over 10,000 rows.
- NFR-P3: A member page MUST hydrate roles and permissions with a bounded number
  of database queries independent of the number of members returned.
- NFR-S1: OIDC signing keys MUST be fetched only from the configured issuer
  discovery document or an explicitly configured HTTPS JWKS URL.
- NFR-S2: Accepted JWT algorithms MUST be an explicit allowlist and MUST NOT
  include `none` or symmetric algorithms for browser identity tokens; unverified
  token claims MUST never select an issuer or discovery endpoint.
- NFR-S3: The API MUST NOT trust tenant IDs, roles, permissions, email addresses,
  or display names supplied by unverified request headers.
- NFR-S4: Tenant tables MUST enable and force PostgreSQL row-level security for
  a non-owner runtime database role. RLS MUST validate a database-signed context
  established from an active Holospan session and membership; a forged or unset
  custom setting MUST deny access.
- NFR-S5: Authentication and authorization errors MUST NOT reveal whether a
  principal, tenant, membership, role, or permission exists.
- NFR-S6: OIDC tokens MUST remain server-side and MUST NOT be persisted after
  session creation. Browser sessions MUST use host-only HttpOnly, Secure,
  SameSite cookies in production and MUST never be written to browser storage.
- NFR-S7: Migration-owner, authentication-runtime, tenant-data-runtime, and
  audit-append database privileges MUST be distinct; runtime roles MUST NOT own
  application tables and MUST NOT update or delete sealed audit records.
- NFR-R1: A failed OIDC discovery or JWKS refresh MUST fail closed; a still-valid
  cached key MAY be used for at most the configured cache lifetime.
- NFR-R2: Administrative mutations and their audit-outbox record MUST commit
  atomically in one database transaction; the independent sealer MUST sequence
  and hash-chain published records.
- NFR-A1: Sign-in and workspace-selection controls MUST be keyboard operable,
  visibly focused, and labelled to WCAG 2.2 AA.
- NFR-O1: Authentication failures MUST be observable by stable reason category
  and request ID, while user-facing responses remain generic.

## Acceptance Criteria

### AC-1: Valid OIDC callback establishes a session (FR-1, FR-2, FR-3, FR-11, FR-16)
Given OIDC is configured and the callback contains a valid code, state, PKCE transaction, and ID token
When the BFF completes the authorization callback
Then it redirects to the configured same-origin frontend
And it sets an opaque host-only HttpOnly session cookie
And `GET /api/v1/identity-access/session` identifies the local immutable principal ID
And no OIDC token or identity-provider password appears in browser storage or the response

### AC-2: Invalid authentication fails closed (FR-1, FR-2, NFR-S2, NFR-S5)
Given a session is missing or the OIDC callback is expired, signed by an unknown key, uses an unapproved algorithm, or has the wrong issuer, audience, nonce, authorized party, or token type
When the client completes login or requests any protected endpoint
Then the response status is 401
And the response code is `AUTHENTICATION_REQUIRED`
And the response does not distinguish the failure cause

### AC-3: Tenant membership is required (FR-4, FR-5, NFR-S3)
Given an authenticated principal without an active membership in tenant A
When the principal requests a tenant-A member endpoint
Then the response status is 403
And no tenant-A member data is returned

### AC-4: Explicit permission permits a tenant action (FR-5, FR-7)
Given an authenticated principal has an active tenant-A role granting `tenant.members.read`
When the principal lists tenant-A members
Then the response status is 200
And every returned membership belongs to tenant A

### AC-5: Tenant admin cannot perform platform administration (FR-6, FR-15, NFR-S5)
Given an authenticated principal is a tenant administrator but has no platform role
When the principal requests `GET /api/v1/platform/identity-access/tenants`
Then the response status is 403
And the response does not reveal platform tenant data

### AC-6: Platform admin creates a tenant (FR-8, FR-10, NFR-R2)
Given an authenticated principal has the platform-administrator role
When the principal creates a tenant using a unique slug, display name, and initial administrator identity
Then the response status is 201
And the tenant is persisted with an active status
And the initial membership and tenant-administrator assignment are persisted
And a tenant-created audit-outbox event is persisted in the same transaction

### AC-7: Role replacement respects boundaries (FR-7, FR-9, FR-16, NFR-R2)
Given a tenant administrator and an active member in the same tenant
When the administrator replaces the member's roles with valid tenant roles
Then the response status is 200
And the effective permissions match exactly the new roles
And a role-replaced audit event is committed atomically

### AC-8: Last tenant administrator is preserved (FR-9)
Given tenant A has exactly one active member with the tenant-administrator role
When that administrator attempts to remove their tenant-administrator role
Then the response status is 409
And the code is `LAST_TENANT_ADMIN_REQUIRED`
And the existing assignment remains unchanged

### AC-9: Bootstrap match is exact and one-time (FR-12, NFR-S3)
Given bootstrap entry `https://id.example|admin-123` is configured
When a verified token has the same subject but a different issuer, or the same issuer but a different subject
Then no platform role is granted
And bootstrap assignment is disabled after the first ordinary platform administrator is established

### AC-10: Anonymous capability access is blocked (FR-13)
Given no bearer token is provided
When the client requests `GET /api/v1/system-catalog/capabilities`
Then the response status is 401
And no capability data is returned

### AC-11: Browser sign-in uses BFF PKCE (FR-1, FR-2, FR-14, NFR-S6, NFR-A1)
Given OIDC client configuration is available
When an unauthenticated user activates the sign-in control
Then the browser starts an authorization-code request containing a PKCE challenge
And state and nonce are bound to a short-lived HttpOnly transaction cookie
And the control is operable by keyboard with a visible focus indicator and accessible name

### AC-12: Workspace selection is membership-bound (FR-4, FR-11, FR-14)
Given an authenticated principal has two active tenant memberships
When the principal selects a workspace
Then subsequent tenant requests send only that selected tenant ID
And selecting any other tenant is rejected by the API

### AC-13: Tenant and platform sessions cannot be confused (FR-15, NFR-S5)
Given a valid tenant-plane session exists
When that cookie is presented to the platform-administration API
Then the response status is 401
And the tenant-plane cookie is not accepted or upgraded

### AC-14: RLS rejects forged context (FR-4, FR-5, NFR-S4, NFR-S7)
Given the non-owner tenant-data runtime database role has no active validated context
When it queries a tenant-scoped table with an unset or manually forged custom setting
Then zero protected rows are returned or the statement is denied
And a context established through the membership-validating database function can access only that tenant

### AC-15: Concurrent final-admin removal is safe (FR-9, NFR-R2)
Given tenant A has two active tenant administrators
When both role removals execute concurrently
Then at most one transaction commits
And tenant A retains at least one active tenant administrator

### AC-16: Audit sealing is tamper evident (FR-10, NFR-S7, NFR-R2)
Given administrative audit-outbox records are pending
When the independent audit writer seals them
Then records receive a monotonic stream sequence, previous digest, event digest, policy version, principal/session type, and sealer identity
And runtime and platform roles cannot update or delete sealed records

### AC-17: Identity lists are bounded and stable (FR-17, NFR-P2, NFR-P3)
Given more than 50 visible tenants or members exist
When an authorized caller requests a list without pagination parameters
Then at most 50 items are returned in stable `(created_at, id)` order
And a next cursor is returned when another page exists
And requesting more than 100 items is rejected with validation status 422
And member roles and permissions are hydrated with a bounded query count

## Edge Cases and Error Scenarios

- EC-1: OIDC discovery times out with no valid cache -> return 503 `IDENTITY_PROVIDER_UNAVAILABLE`; do not create a session.
- EC-2: JWKS rotates and `kid` is unknown -> refresh once, then return the generic 401 response if still unknown.
- EC-3: `(issuer, subject)` already exists -> update only allowed profile fields and last-seen time; do not create a duplicate.
- EC-4: Tenant slug conflicts under concurrency -> one transaction succeeds and the other returns 409 `TENANT_SLUG_CONFLICT`.
- EC-5: Database is unavailable -> return 503 with a generic message and no SQL details.
- EC-6: Requested tenant ID is malformed or not visible -> return the same 403 response used for absent membership.
- EC-7: Role replacement has an empty role list -> allow it only after locking the tenant administrator set and proving another active tenant administrator remains.
- EC-8: A suspended principal or membership presents a valid token -> return 403 and no tenant data.
- EC-9: Audit-event persistence fails -> roll back the corresponding administrative mutation.
- EC-10: OIDC is not configured -> the public config endpoint reports `enabled: false`; protected endpoints return 503 `IDENTITY_NOT_CONFIGURED`.
- EC-11: Callback state or transaction cookie mismatch -> clear the transaction cookie and return the generic authentication failure without exchanging the code.
- EC-12: ID token is presented as API bearer authentication -> return 401 and do not create or resume a session.

## API Contracts

Protected browser calls require the correct host-only Holospan session cookie.
State-changing calls additionally require `X-CSRF-Token`. Tenant-scoped calls
also require `X-Holospan-Tenant-ID: <uuid>` as a requested scope, never as
authority. Responses use the existing Holospan envelopes.

```typescript
interface OidcClientConfig {
  enabled: boolean;
  authority?: string;
  clientId?: string;
  scope?: string;
  redirectUri?: string;
  postLogoutRedirectUri?: string;
}

interface PrincipalSummary {
  id: string;
  email?: string;
  displayName?: string;
  status: "active" | "suspended";
}

interface MembershipSummary {
  tenantId: string;
  tenantSlug: string;
  tenantName: string;
  roles: string[];
  permissions: string[];
  status: "active" | "suspended";
}

interface SessionContext {
  principal: PrincipalSummary;
  memberships: MembershipSummary[];
  platformRoles: string[];
  platformPermissions: string[];
  selectedTenantId?: string;
}

interface CreateTenantRequest {
  slug: string;        // lowercase letters, digits and hyphens; 3-63 chars
  displayName: string; // 1-120 chars
  initialAdmin: {
    issuer: string;
    subject: string;
    email?: string;
    displayName?: string;
  };
}

interface ReplaceMemberRolesRequest {
  roleIds: string[];   // unique UUIDs, maximum 20
}

interface CursorPage<T> {
  items: T[];
  nextCursor?: string; // opaque server-generated cursor
}

interface ApiError {
  error: {
    code: string;
    message: string;
    details: Array<{ field?: string; code: string; message: string }>;
    requestId: string;
    timestamp: string;
  };
}
```

Endpoints:

- `GET /api/v1/identity-access/oidc-config` -> 200 non-secret status/configuration (anonymous).
- `GET /api/v1/identity-access/login` -> 302 to the configured tenant IdP (anonymous).
- `GET /api/v1/identity-access/callback` -> 302 to the fixed tenant frontend (anonymous callback).
- `GET /api/v1/identity-access/session` -> 200 `SessionContext`; 401; 503.
- `DELETE /api/v1/identity-access/session` -> 204 and cookie clearing; 401; 403 CSRF.
- `GET /api/v1/identity-access/tenants?limit=50&cursor=...` -> 200 `CursorPage<TenantSummary>`; 401; 422.
- `GET /api/v1/platform/identity-access/tenants?limit=50&cursor=...` -> 200 `CursorPage<TenantSummary>`; 401; 403; 422.
- `POST /api/v1/platform/identity-access/tenants` -> 201 tenant plus initial admin; 401; 403; 409; 422; 503.
- `GET /api/v1/identity-access/tenants/{tenantId}/members?limit=50&cursor=...` -> 200 `CursorPage<MemberSummary>`; 401; 403; 422; 503.
- `PUT /api/v1/identity-access/tenants/{tenantId}/members/{membershipId}/roles` -> 200 membership; 401; 403; 404; 409; 422; 503.

## Data Models

### Principal
| Field | Type | Constraints |
|---|---|---|
| id | UUID | PK, immutable |
| issuer | varchar(512) | not null, normalized URL |
| subject | varchar(255) | not null, opaque |
| email | varchar(320) | nullable, profile only, never identity key |
| display_name | varchar(120) | nullable |
| status | enum | active/suspended |
| last_seen_at | timestamptz | not null |
| created_at / updated_at | timestamptz | not null |
| version | integer | not null, optimistic lock |

Unique index: `(issuer, subject)`.

### Tenant
| Field | Type | Constraints |
|---|---|---|
| id | UUID | PK, immutable |
| slug | varchar(63) | unique, lowercase DNS-label form |
| display_name | varchar(120) | not null |
| status | enum | active/suspended |
| created_by | UUID | FK principal |
| created_at / updated_at | timestamptz | not null |
| version | integer | not null, optimistic lock |

### Membership
| Field | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| tenant_id | UUID | FK tenant, tenant scope |
| principal_id | UUID | FK principal |
| status | enum | active/suspended |
| created_at / updated_at | timestamptz | not null |
| version | integer | not null |

Unique index: `(tenant_id, principal_id)`; lookup indexes start with
`tenant_id` for tenant listings and `principal_id` for session lookup.

### TenantRole
| Field | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| key | varchar(80) | stable machine key |
| display_name | varchar(120) | not null |
| tenant_id | UUID | nullable; custom roles reserved for later |
| is_system | boolean | not null |
| created_at / updated_at | timestamptz | not null |

Unique indexes: global `(scope, key)` where `tenant_id IS NULL`; tenant-local
`(tenant_id, key)` where `tenant_id IS NOT NULL`.

### TenantPermission
| Field | Type | Constraints |
|---|---|---|
| key | varchar(120) | PK, stable machine key |
| description | varchar(255) | not null |

### TenantRolePermission
Composite PK `(role_id, permission_key)` with FKs to TenantRole and TenantPermission.

### MembershipRole
Composite PK `(membership_id, role_id)` with an FK to TenantRole, making
platform-role assignment structurally impossible.

### PlatformRole / PlatformPermission / PlatformRolePermission
Physically separate platform tables equivalent to the tenant role and
permission tables. This prevents cross-scope foreign keys by construction.

### PrincipalPlatformRole
Composite PK `(principal_id, role_id)` with an FK to PlatformRole.

### BrowserSession
| Field | Type | Constraints |
|---|---|---|
| token_digest | bytea | unique; raw opaque token exists only in secure cookie |
| principal_id | UUID | FK principal |
| plane | enum | tenant/platform; immutable |
| csrf_digest | bytea | not null |
| expires_at / revoked_at | timestamptz | expiry and revocation |
| auth_time / created_at / last_seen_at | timestamptz | session evidence |

### AuthorizationAuditOutbox
| Field | Type | Constraints |
|---|---|---|
| id | UUID | PK |
| tenant_id | UUID | nullable FK tenant |
| actor_principal_id | UUID | nullable FK principal |
| action | varchar(120) | not null |
| target_type / target_id | varchar | nullable target reference |
| outcome | enum | allowed/denied/succeeded/failed |
| reason_code | varchar(120) | not null, non-secret |
| request_id | varchar(128) | not null |
| principal_type / session_type | varchar | not null |
| policy_version | varchar | not null |
| before_digest / after_digest | bytea | nullable mutation evidence |
| metadata | jsonb | sanitized structured metadata |
| occurred_at | timestamptz | immutable, not null |

### SealedAuthorizationAuditEvent
Contains all outbox evidence plus `stream_id`, monotonic `sequence`,
`previous_digest`, `event_digest`, `sealed_at`, and `sealer_identity`. Runtime
roles receive no UPDATE or DELETE privilege. Indexes lead with stream/tenant and time.

## Out of Scope

- OS-1: Password authentication or password storage; identity remains external via OIDC.
- OS-2: MFA enrollment and recovery; enforcement belongs to the configured IdP for this slice.
- OS-3: SCIM provisioning and group-to-role synchronization; separate enterprise identity spec.
- OS-4: Tenant invitations and email delivery; initial administrators use explicit API/CLI provisioning.
- OS-5: Custom role CRUD; the schema permits future tenant roles, but only seeded system roles are assignable now.
- OS-6: Admin impersonation; prohibited until a dedicated consent, audit, and approval design exists.
- OS-7: Fine-grained resource ABAC beyond tenant and platform scope; separate assurance-resource authorization spec.
- OS-8: Billing plans, quotas, and entitlements; not part of identity authorization.
- OS-9: Session revocation at the IdP; access-token lifetime and revocation remain provider policy.
- OS-10: Service, workload, support, emergency, and break-glass principals; each requires a separate non-interactive identity and approval design.
- OS-11: Multiple tenant OIDC issuers in one deployment; the first slice uses one explicitly configured tenant issuer and one explicitly configured platform issuer.
- OS-12: The platform-operations frontend; this slice provides the separately hosted backend contract only.
