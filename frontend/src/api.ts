import { z } from 'zod'

const metaSchema = z.object({
  requestId: z.string(),
  timestamp: z.string(),
})

const capabilitySchema = z.object({
  id: z.string(),
  name: z.string(),
  status: z.enum(['available', 'planned']),
  description: z.string(),
})

const capabilitiesEnvelopeSchema = z.object({
  data: z.object({
    service: z.string(),
    version: z.string(),
    deploymentMode: z.string(),
    capabilities: z.array(capabilitySchema),
  }),
  meta: metaSchema,
})

const oidcConfigEnvelopeSchema = z.object({
  data: z.object({
    enabled: z.boolean(),
    authority: z.string().optional(),
    clientId: z.string().optional(),
    scope: z.string().optional(),
    redirectUri: z.string().optional(),
  }),
  meta: metaSchema,
})

const membershipSchema = z.object({
  id: z.string().uuid(),
  tenantId: z.string().uuid(),
  tenantSlug: z.string(),
  tenantName: z.string(),
  roles: z.array(z.string()),
  permissions: z.array(z.string()),
  status: z.enum(['active', 'suspended']),
})

const sessionEnvelopeSchema = z.object({
  data: z.object({
    principal: z.object({
      id: z.string().uuid(),
      email: z.string().optional().nullable(),
      displayName: z.string().optional().nullable(),
      status: z.enum(['active', 'suspended']),
    }),
    memberships: z.array(membershipSchema),
    platformRoles: z.array(z.string()),
    platformPermissions: z.array(z.string()),
    selectedTenantId: z.string().uuid().optional().nullable(),
    csrfToken: z.string().min(1),
  }),
  meta: metaSchema,
})

const errorEnvelopeSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    requestId: z.string().optional(),
  }),
})

export type CapabilitiesEnvelope = z.infer<typeof capabilitiesEnvelopeSchema>
export type OidcConfigEnvelope = z.infer<typeof oidcConfigEnvelopeSchema>
export type SessionEnvelope = z.infer<typeof sessionEnvelopeSchema>
export type Membership = z.infer<typeof membershipSchema>

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function parseResponse<T>(response: Response, schema: z.ZodType<T>): Promise<T> {
  const body: unknown = await response.json()
  if (!response.ok) {
    const parsed = errorEnvelopeSchema.safeParse(body)
    throw new ApiError(
      response.status,
      parsed.success ? parsed.data.error.code : 'UNEXPECTED_RESPONSE',
      parsed.success ? parsed.data.error.message : 'The server returned an unexpected response.',
    )
  }
  return schema.parse(body)
}

export async function fetchOidcConfig(signal?: AbortSignal): Promise<OidcConfigEnvelope> {
  const response = await fetch('/api/v1/identity-access/oidc-config', {
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
    signal,
  })
  return parseResponse(response, oidcConfigEnvelopeSchema)
}

export async function fetchSession(signal?: AbortSignal): Promise<SessionEnvelope> {
  const response = await fetch('/api/v1/identity-access/session', {
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
    signal,
  })
  return parseResponse(response, sessionEnvelopeSchema)
}

export async function fetchCapabilities(
  signal?: AbortSignal,
  tenantId?: string,
): Promise<CapabilitiesEnvelope> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (tenantId) headers['X-Holospan-Tenant-ID'] = tenantId
  const response = await fetch('/api/v1/system-catalog/capabilities', {
    credentials: 'same-origin',
    headers,
    signal,
  })
  return parseResponse(response, capabilitiesEnvelopeSchema)
}

export async function logout(csrfToken: string): Promise<void> {
  const response = await fetch('/api/v1/identity-access/session', {
    method: 'DELETE',
    credentials: 'same-origin',
    headers: { 'X-CSRF-Token': csrfToken },
  })
  if (!response.ok) {
    const body: unknown = await response.json()
    const parsed = errorEnvelopeSchema.safeParse(body)
    throw new ApiError(
      response.status,
      parsed.success ? parsed.data.error.code : 'LOGOUT_FAILED',
      parsed.success ? parsed.data.error.message : 'Sign out failed.',
    )
  }
}
