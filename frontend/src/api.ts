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
    expiresAt: z.string().datetime({ offset: true }),
  }),
  meta: metaSchema,
})

const logoutEnvelopeSchema = z.object({
  data: z.object({ redirectUri: z.string().min(1) }),
  meta: metaSchema,
})

const systemSummarySchema = z.object({
  id: z.string().uuid(),
  tenantId: z.string().uuid(),
  displayName: z.string(),
  slug: z.string(),
  description: z.string().optional().nullable(),
  systemType: z.enum(['agent', 'rag', 'workflow', 'model', 'api', 'other']),
  lifecycleStage: z.enum(['development', 'staging', 'production']),
  status: z.literal('draft'),
  createdBy: z.string().uuid(),
  createdAt: z.string(),
  updatedAt: z.string(),
})

const systemsEnvelopeSchema = z.object({
  data: z.object({ items: z.array(systemSummarySchema) }),
  meta: metaSchema,
})

const systemEnvelopeSchema = z.object({
  data: systemSummarySchema,
  meta: metaSchema,
})

const sourceSummarySchema = z.object({
  id: z.string().uuid(),
  systemId: z.string().uuid(),
  kind: z.enum(['context_document', 'api_contract']),
  originalFilename: z.string(),
  declaredMediaType: z.string(),
  detectedMediaType: z.string(),
  byteSize: z.number().int().positive(),
  sha256: z.string().regex(/^[0-9a-f]{64}$/),
  status: z.literal('stored'),
  createdBy: z.string().uuid(),
  createdAt: z.string(),
})

const sourcesEnvelopeSchema = z.object({
  data: z.object({ items: z.array(sourceSummarySchema) }),
  meta: metaSchema,
})

const sourceEnvelopeSchema = z.object({
  data: sourceSummarySchema,
  meta: metaSchema,
})

const evidenceCitationSchema = z.object({
  source_id: z.string().uuid(),
  locator: z.string(),
  content_sha256: z.string().regex(/^[0-9a-f]{64}$/),
})

const contextClaimSchema = z.object({
  subject_key: z.string(),
  claim_type: z.string(),
  value: z.unknown(),
  status: z.enum(['supported', 'conflicting', 'unknown', 'rejected']),
  confidence: z.number().min(0).max(1),
  extraction_method: z.enum(['deterministic', 'model', 'human']),
  citations: z.array(evidenceCitationSchema),
})

const componentContextSchema = z.object({
  key: z.string(),
  display_name: z.string(),
  purpose: z.string().optional().nullable(),
  capabilities: z.array(z.string()),
  inputs: z.array(z.string()),
  outputs: z.array(z.string()),
  tools: z.array(z.string()),
  dependencies: z.array(z.string()),
  policies: z.array(z.string()),
})

const contextGapSchema = z.object({
  code: z.string(),
  message: z.string(),
  source_id: z.string().uuid().optional().nullable(),
  locator: z.string().optional().nullable(),
})

const contextContentSchema = z.object({
  tenant_id: z.string().uuid(),
  system_id: z.string().uuid(),
  source_manifest_sha256: z.string().regex(/^[0-9a-f]{64}$/),
  system_name: z.string(),
  status: z.literal('draft'),
  schema_version: z.literal('1.0'),
  claims: z.array(contextClaimSchema),
  components: z.array(componentContextSchema),
  gaps: z.array(contextGapSchema),
  generator: z.literal('deterministic_discovery_v1'),
  content_sha256: z.string().regex(/^[0-9a-f]{64}$/),
})

const contextSnapshotSchema = z.object({
  id: z.string().uuid(),
  systemId: z.string().uuid(),
  version: z.number().int().positive(),
  rowVersion: z.number().int().positive(),
  status: z.enum(['draft', 'approved', 'rejected', 'revoked']),
  sha256: z.string().regex(/^[0-9a-f]{64}$/),
  criticScore: z.number().min(0).max(1),
  content: contextContentSchema,
  approvedBy: z.string().uuid().optional().nullable(),
  approvedAt: z.string().optional().nullable(),
  createdAt: z.string(),
})

const contextSnapshotsEnvelopeSchema = z.object({
  data: z.object({ items: z.array(contextSnapshotSchema) }),
  meta: metaSchema,
})

const discoveryRunSchema = z.object({
  id: z.string().uuid(),
  systemId: z.string().uuid(),
  status: z.enum(['queued', 'discovering', 'context_review', 'planning', 'generating', 'scenario_review', 'published', 'paused', 'failed', 'cancelled']),
  currentStage: z.string(),
  sourceIds: z.array(z.string().uuid()),
  contextSnapshot: contextSnapshotSchema.optional().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
})

const discoveryRunEnvelopeSchema = z.object({ data: discoveryRunSchema, meta: metaSchema })
const contextSnapshotEnvelopeSchema = z.object({ data: contextSnapshotSchema, meta: metaSchema })

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
export type LogoutEnvelope = z.infer<typeof logoutEnvelopeSchema>
export type Membership = z.infer<typeof membershipSchema>
export type SystemSummary = z.infer<typeof systemSummarySchema>
export type SystemsEnvelope = z.infer<typeof systemsEnvelopeSchema>
export type SystemEnvelope = z.infer<typeof systemEnvelopeSchema>
export type SourceKind = z.infer<typeof sourceSummarySchema>['kind']
export type SourceSummary = z.infer<typeof sourceSummarySchema>
export type SourcesEnvelope = z.infer<typeof sourcesEnvelopeSchema>
export type SourceEnvelope = z.infer<typeof sourceEnvelopeSchema>
export type ContextSnapshot = z.infer<typeof contextSnapshotSchema>
export type ContextSnapshotsEnvelope = z.infer<typeof contextSnapshotsEnvelopeSchema>
export type DiscoveryRunEnvelope = z.infer<typeof discoveryRunEnvelopeSchema>
export type CreateSystemInput = {
  displayName: string
  slug: string
  description?: string | null
  systemType: SystemSummary['systemType']
  lifecycleStage: SystemSummary['lifecycleStage']
}

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

export const SESSION_EXPIRED_EVENT = 'holospan:session-expired'

function notifySessionExpired(response: Response) {
  if (response.status === 401 && typeof window !== 'undefined') {
    window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT))
  }
}

async function parseResponse<T>(response: Response, schema: z.ZodType<T>): Promise<T> {
  if (!response.ok) notifySessionExpired(response)
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

export async function fetchSystems(
  tenantId: string,
  signal?: AbortSignal,
): Promise<SystemsEnvelope> {
  const response = await fetch('/api/v1/system-context/systems?limit=50', {
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      'X-Holospan-Tenant-ID': tenantId,
    },
    signal,
  })
  return parseResponse(response, systemsEnvelopeSchema)
}

export async function fetchSystem(
  tenantId: string,
  systemId: string,
  signal?: AbortSignal,
): Promise<SystemEnvelope> {
  const response = await fetch(`/api/v1/system-context/systems/${systemId}`, {
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      'X-Holospan-Tenant-ID': tenantId,
    },
    signal,
  })
  return parseResponse(response, systemEnvelopeSchema)
}

export async function fetchSystemSources(
  tenantId: string,
  systemId: string,
  signal?: AbortSignal,
): Promise<SourcesEnvelope> {
  const response = await fetch(`/api/v1/system-context/systems/${systemId}/sources?limit=50`, {
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      'X-Holospan-Tenant-ID': tenantId,
    },
    signal,
  })
  return parseResponse(response, sourcesEnvelopeSchema)
}

export async function uploadSystemSource(
  tenantId: string,
  systemId: string,
  csrfToken: string,
  kind: SourceKind,
  file: File,
): Promise<SourceEnvelope> {
  const body = new FormData()
  body.set('kind', kind)
  body.set('file', file)
  const response = await fetch(`/api/v1/system-context/systems/${systemId}/sources`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      'X-Holospan-Tenant-ID': tenantId,
      'X-CSRF-Token': csrfToken,
    },
    body,
  })
  return parseResponse(response, sourceEnvelopeSchema)
}

export async function createSystem(
  tenantId: string,
  csrfToken: string,
  input: CreateSystemInput,
): Promise<SystemEnvelope> {
  const response = await fetch('/api/v1/system-context/systems', {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-Holospan-Tenant-ID': tenantId,
      'X-CSRF-Token': csrfToken,
    },
    body: JSON.stringify(input),
  })
  return parseResponse(response, systemEnvelopeSchema)
}

export async function fetchContextSnapshots(
  tenantId: string,
  systemId: string,
  signal?: AbortSignal,
): Promise<ContextSnapshotsEnvelope> {
  const response = await fetch(`/api/v1/systems/${systemId}/context-snapshots?limit=20`, {
    credentials: 'same-origin',
    headers: { Accept: 'application/json', 'X-Holospan-Tenant-ID': tenantId },
    signal,
  })
  return parseResponse(response, contextSnapshotsEnvelopeSchema)
}

export async function startContextDiscovery(
  tenantId: string,
  systemId: string,
  csrfToken: string,
  sourceIds: string[],
): Promise<DiscoveryRunEnvelope> {
  const response = await fetch(`/api/v1/systems/${systemId}/assurance-generation/runs`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-Holospan-Tenant-ID': tenantId,
      'X-CSRF-Token': csrfToken,
      'Idempotency-Key': `discovery-${crypto.randomUUID()}`,
    },
    body: JSON.stringify({ sourceIds, budgetProfile: 'balanced' }),
  })
  return parseResponse(response, discoveryRunEnvelopeSchema)
}

export async function reviewContextSnapshot(
  tenantId: string,
  snapshotId: string,
  csrfToken: string,
  input: { decision: 'approve' | 'reject'; comment: string; expectedVersion: number },
) {
  const response = await fetch(`/api/v1/context-snapshots/${snapshotId}/review`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-Holospan-Tenant-ID': tenantId,
      'X-CSRF-Token': csrfToken,
    },
    body: JSON.stringify(input),
  })
  return parseResponse(response, contextSnapshotEnvelopeSchema)
}

export async function logout(): Promise<LogoutEnvelope> {
  const response = await fetch('/api/v1/identity-access/session', {
    method: 'DELETE',
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
  })
  return parseResponse(response, logoutEnvelopeSchema)
}
