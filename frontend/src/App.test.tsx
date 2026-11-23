import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import App from './App'
import type { ContextSnapshot } from './api'

const meta = { requestId: 'test-request', timestamp: '2026-11-22T00:00:00Z' }

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><App /></QueryClientProvider>)
}

afterEach(() => {
  vi.unstubAllGlobals()
  window.history.replaceState({}, '', '/')
})

it('fails closed with setup guidance when OIDC is not configured', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({ data: { enabled: false }, meta }),
  }))

  renderApp()

  expect(await screen.findByRole('heading', { name: /connect your identity provider/i })).toBeInTheDocument()
  expect(screen.getByText('Identity configuration required')).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: /continue with organization sso/i })).not.toBeInTheDocument()
})

it('offers BFF sign-in when OIDC is configured and no session exists', async () => {
  const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    if (url.endsWith('/oidc-config')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { enabled: true }, meta }) })
    }
    return Promise.resolve({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ error: { code: 'AUTHENTICATION_REQUIRED', message: 'Authentication is required.' } }),
    })
  })
  vi.stubGlobal('fetch', fetchMock)

  renderApp()

  const signIn = await screen.findByRole('link', { name: /continue with organization sso/i })
  expect(signIn).toHaveAttribute('href', '/api/v1/identity-access/login')
})

it('renders the protected workspace after session verification', async () => {
  const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    if (url.endsWith('/oidc-config')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { enabled: true }, meta }) })
    }
    if (url.endsWith('/session')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          data: {
            principal: { id: '019aca05-8233-7cc1-b2cc-9727fc367b6d', email: 'user@example.com', displayName: 'Test User', status: 'active' },
            memberships: [{
              id: '019aca05-8233-7cc1-b2cc-9727fc367b6e',
              tenantId: '019aca05-8233-7cc1-b2cc-9727fc367b6f',
              tenantSlug: 'holospan-lab',
              tenantName: 'Holospan Lab',
              roles: ['tenant_admin'],
              permissions: ['tenant.members.read'],
              status: 'active',
            }],
            platformRoles: [],
            platformPermissions: [],
            csrfToken: 'csrf-test-token',
            expiresAt: '2999-11-22T01:00:00Z',
          },
          meta,
        }),
      })
    }
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({
        data: {
          service: 'holospan-api',
          version: '0.1.0',
          deploymentMode: 'docker-compose',
          capabilities: [{ id: 'health', name: 'Health checks', status: 'available', description: 'Operational probes' }],
        },
        meta,
      }),
    })
  })
  vi.stubGlobal('fetch', fetchMock)

  renderApp()

  expect(await screen.findByRole('heading', { name: /prove what your agents can safely do/i })).toBeInTheDocument()
  expect(await screen.findByText('Service available')).toBeInTheDocument()
  expect(screen.getByLabelText('Current workspace')).toHaveValue('019aca05-8233-7cc1-b2cc-9727fc367b6f')
  expect(screen.getByText('Test User')).toBeInTheDocument()
})

it('AC-1 AC-2 AC-8 makes navigation and create-system controls functional without deployment jargon', async () => {
  const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    if (url.endsWith('/oidc-config')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { enabled: true }, meta }) })
    }
    if (url.endsWith('/session')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          data: {
            principal: { id: '019aca05-8233-7cc1-b2cc-9727fc367b6d', email: 'user@example.com', displayName: 'Test User', status: 'active' },
            memberships: [{
              id: '019aca05-8233-7cc1-b2cc-9727fc367b6e',
              tenantId: '019aca05-8233-7cc1-b2cc-9727fc367b6f',
              tenantSlug: 'holospan-lab',
              tenantName: 'Holospan Lab',
              roles: ['tenant_admin'],
              permissions: ['system_context.systems.read', 'system_context.systems.manage'],
              status: 'active',
            }],
            platformRoles: [],
            platformPermissions: [],
            csrfToken: 'csrf-test-token',
            expiresAt: '2999-11-22T01:00:00Z',
          },
          meta,
        }),
      })
    }
    if (url.includes('/system-context/systems')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { items: [] }, meta }) })
    }
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({
        data: {
          service: 'holospan-api',
          version: '0.1.0',
          deploymentMode: 'docker-compose',
          capabilities: [{ id: 'health', name: 'Health checks', status: 'available', description: 'Operational probes' }],
        },
        meta,
      }),
    })
  })
  vi.stubGlobal('fetch', fetchMock)

  renderApp()

  expect(await screen.findByRole('heading', { name: /prove what your agents can safely do/i })).toBeInTheDocument()
  expect(screen.queryByText(/EC2|Docker Compose|validation topology/i)).not.toBeInTheDocument()

  fireEvent.click(screen.getByRole('button', { name: 'Systems' }))
  expect(await screen.findByRole('heading', { name: 'Systems' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /create system/i })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Systems' })).toHaveAttribute('aria-current', 'page')

  fireEvent.click(screen.getByRole('button', { name: /create system/i }))
  expect(await screen.findByRole('dialog', { name: /create a system/i })).toBeInTheDocument()
  expect(screen.getByLabelText(/^system name$/i)).toHaveFocus()
})

it('AC-3 submits a tenant-scoped system with CSRF and displays the result', async () => {
  const tenantId = '019aca05-8233-7cc1-b2cc-9727fc367b6f'
  const created = {
    id: '019aca05-8233-7cc1-b2cc-9727fc367b70',
    tenantId,
    displayName: 'Claims Copilot',
    slug: 'claims-copilot',
    description: 'Assists claims reviewers.',
    systemType: 'agent',
    lifecycleStage: 'development',
    status: 'draft',
    createdBy: '019aca05-8233-7cc1-b2cc-9727fc367b6d',
    createdAt: '2026-11-22T00:00:00Z',
    updatedAt: '2026-11-22T00:00:00Z',
  }
  let systems: typeof created[] = []
  const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    if (url.endsWith('/oidc-config')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { enabled: true }, meta }) })
    if (url.endsWith('/session')) return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({
        data: {
          principal: { id: created.createdBy, email: 'user@example.com', displayName: 'Test User', status: 'active' },
          memberships: [{ id: '019aca05-8233-7cc1-b2cc-9727fc367b6e', tenantId, tenantSlug: 'holospan-lab', tenantName: 'Holospan Lab', roles: ['tenant_admin'], permissions: ['system_context.systems.read', 'system_context.systems.manage'], status: 'active' }],
          platformRoles: [], platformPermissions: [], csrfToken: 'csrf-test-token', expiresAt: '2999-11-22T01:00:00Z',
        },
        meta,
      }),
    })
    if (url.includes('/system-context/systems') && init?.method === 'POST') {
      expect(init.headers).toMatchObject({ 'X-Holospan-Tenant-ID': tenantId, 'X-CSRF-Token': 'csrf-test-token' })
      systems = [created]
      return Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve({ data: created, meta }) })
    }
    if (url.includes('/system-context/systems')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { items: systems }, meta }) })
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { service: 'holospan-api', version: '0.1.0', deploymentMode: 'docker-compose', capabilities: [] }, meta }) })
  })
  vi.stubGlobal('fetch', fetchMock)

  renderApp()
  await screen.findByRole('heading', { name: /prove what your agents can safely do/i })
  fireEvent.click(screen.getByRole('button', { name: 'Systems' }))
  fireEvent.click(await screen.findByRole('button', { name: /create system/i }))
  fireEvent.change(screen.getByLabelText(/^system name$/i), { target: { value: 'Claims Copilot' } })
  fireEvent.change(screen.getByLabelText(/description/i), { target: { value: 'Assists claims reviewers.' } })
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^create system$/i }))

  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(await screen.findByText('Claims Copilot')).toBeInTheDocument()
})

it('opens system details and uploads an API contract as an additive source', async () => {
  const tenantId = '019aca05-8233-7cc1-b2cc-9727fc367b6f'
  const systemId = '019aca05-8233-7cc1-b2cc-9727fc367b70'
  const system = {
    id: systemId,
    tenantId,
    displayName: 'Claims Copilot',
    slug: 'claims-copilot',
    description: 'Assists claims reviewers.',
    systemType: 'agent',
    lifecycleStage: 'development',
    status: 'draft',
    createdBy: '019aca05-8233-7cc1-b2cc-9727fc367b6d',
    createdAt: '2026-11-22T00:00:00Z',
    updatedAt: '2026-11-22T00:00:00Z',
  }
  const source = {
    id: '019aca05-8233-7cc1-b2cc-9727fc367b71',
    systemId,
    kind: 'api_contract',
    originalFilename: 'openapi.yaml',
    declaredMediaType: 'application/yaml',
    detectedMediaType: 'application/yaml',
    byteSize: 13,
    sha256: 'a'.repeat(64),
    status: 'stored',
    createdBy: system.createdBy,
    createdAt: '2026-11-23T00:00:00Z',
  }
  let sources: typeof source[] = []
  const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    if (url.endsWith('/oidc-config')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { enabled: true }, meta }) })
    if (url.endsWith('/session')) return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({
        data: {
          principal: { id: system.createdBy, email: 'user@example.com', displayName: 'Test User', status: 'active' },
          memberships: [{
            id: '019aca05-8233-7cc1-b2cc-9727fc367b6e', tenantId, tenantSlug: 'holospan-lab', tenantName: 'Holospan Lab', roles: ['tenant_admin'],
            permissions: ['system_context.systems.read', 'system_context.systems.manage', 'system_context.sources.read', 'system_context.sources.manage'], status: 'active',
          }],
          platformRoles: [], platformPermissions: [], csrfToken: 'csrf-test-token', expiresAt: '2999-11-22T01:00:00Z',
        },
        meta,
      }),
    })
    if (url.includes(`/systems/${systemId}/sources`) && init?.method === 'POST') {
      expect(init.headers).toMatchObject({ 'X-Holospan-Tenant-ID': tenantId, 'X-CSRF-Token': 'csrf-test-token' })
      expect(init.body).toBeInstanceOf(FormData)
      sources = [source]
      return Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve({ data: source, meta }) })
    }
    if (url.includes(`/systems/${systemId}/sources`)) return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { items: sources }, meta }) })
    if (url.endsWith(`/systems/${systemId}`)) return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: system, meta }) })
    if (url.includes('/system-context/systems')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { items: [system] }, meta }) })
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { service: 'holospan-api', version: '0.1.0', deploymentMode: 'docker-compose', capabilities: [] }, meta }) })
  })
  vi.stubGlobal('fetch', fetchMock)

  renderApp()
  await screen.findByRole('heading', { name: /prove what your agents can safely do/i })
  fireEvent.click(screen.getByRole('button', { name: 'Systems' }))
  fireEvent.click(await screen.findByRole('button', { name: /open claims copilot/i }))

  expect(await screen.findByRole('heading', { name: 'Claims Copilot' })).toBeInTheDocument()
  expect(screen.getByText('Code repository')).toBeInTheDocument()
  expect(screen.getByText('Context & contracts')).toBeInTheDocument()
  expect(screen.getByText('Runtime endpoint')).toBeInTheDocument()
  expect(screen.getByText('Telemetry')).toBeInTheDocument()
  expect(screen.getAllByText('Planned')).toHaveLength(3)

  fireEvent.click(screen.getByLabelText('API contract'))
  fireEvent.change(screen.getByLabelText('Source file'), {
    target: { files: [new File(['openapi: 3.1'], 'openapi.yaml', { type: 'application/yaml' })] },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Upload source' }))

  const inventory = screen.getByRole('region', { name: 'Connected sources' })
  expect(await within(inventory).findByText('openapi.yaml')).toBeInTheDocument()
})

it('discovers cited context from selected evidence and records human approval', async () => {
  const tenantId = '019aca05-8233-7cc1-b2cc-9727fc367b6f'
  const systemId = '019aca05-8233-7cc1-b2cc-9727fc367b70'
  const sourceId = '019aca05-8233-7cc1-b2cc-9727fc367b71'
  const snapshotId = '019aca05-8233-7cc1-b2cc-9727fc367b72'
  const principalId = '019aca05-8233-7cc1-b2cc-9727fc367b6d'
  const system = {
    id: systemId, tenantId, displayName: 'Travel Agent', slug: 'travel-agent', description: 'Plans trips.',
    systemType: 'agent', lifecycleStage: 'development', status: 'draft', createdBy: principalId,
    createdAt: '2026-11-23T00:00:00Z', updatedAt: '2026-11-23T00:00:00Z',
  }
  const source = {
    id: sourceId, systemId, kind: 'context_document', originalFilename: 'travel-prd.md',
    declaredMediaType: 'text/markdown', detectedMediaType: 'text/markdown', byteSize: 128,
    sha256: 'a'.repeat(64), status: 'stored', createdBy: principalId, createdAt: '2026-11-23T00:00:00Z',
  }
  const baseSnapshot: ContextSnapshot = {
    id: snapshotId, systemId, version: 1, rowVersion: 1, status: 'draft', sha256: 'b'.repeat(64), criticScore: 1,
    content: {
      tenant_id: tenantId, system_id: systemId, source_manifest_sha256: 'c'.repeat(64), system_name: 'Travel Agent',
      status: 'draft', schema_version: '1.0', generator: 'deterministic_discovery_v1', content_sha256: 'b'.repeat(64),
      claims: [{
        subject_key: 'trip-planner', claim_type: 'capability', value: 'Search hotels by destination and budget.',
        status: 'supported', confidence: 1, extraction_method: 'deterministic',
        citations: [{ source_id: sourceId, locator: 'lines:1-3#line:3', content_sha256: 'a'.repeat(64) }],
      }],
      components: [{
        key: 'trip-planner', display_name: 'Trip Planner', purpose: 'Plan customer travel.',
        capabilities: ['Search hotels by destination and budget.'], inputs: [], outputs: [], tools: [], dependencies: [], policies: [],
      }],
      gaps: [],
    },
    approvedBy: null, approvedAt: null, createdAt: '2026-11-23T00:00:00Z',
  }
  let snapshots: Array<typeof baseSnapshot> = []
  const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    if (url.endsWith('/oidc-config')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { enabled: true }, meta }) })
    if (url.endsWith('/session')) return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ data: {
        principal: { id: principalId, email: 'reviewer@example.com', displayName: 'Context Reviewer', status: 'active' },
        memberships: [{
          id: '019aca05-8233-7cc1-b2cc-9727fc367b6e', tenantId, tenantSlug: 'lab', tenantName: 'Holospan Lab', roles: ['tenant_admin'],
          permissions: ['system_context.systems.read', 'system_context.sources.read', 'assurance_generation.context.read', 'assurance_generation.context.generate', 'assurance_generation.context.review'], status: 'active',
        }],
        platformRoles: [], platformPermissions: [], csrfToken: 'csrf-test-token', expiresAt: '2999-11-22T01:00:00Z',
      }, meta }),
    })
    if (url.includes(`/systems/${systemId}/assurance-generation/runs`) && init?.method === 'POST') {
      expect(init.headers).toMatchObject({ 'X-Holospan-Tenant-ID': tenantId, 'X-CSRF-Token': 'csrf-test-token' })
      snapshots = [baseSnapshot]
      return Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve({ data: {
        id: '019aca05-8233-7cc1-b2cc-9727fc367b73', systemId, status: 'context_review', currentStage: 'review_context', sourceIds: [sourceId], contextSnapshot: baseSnapshot,
        createdAt: '2026-11-23T00:00:00Z', updatedAt: '2026-11-23T00:00:00Z',
      }, meta }) })
    }
    if (url.includes(`/context-snapshots/${snapshotId}/review`) && init?.method === 'POST') {
      snapshots = [{ ...baseSnapshot, status: 'approved', rowVersion: 2, approvedBy: principalId, approvedAt: '2026-11-23T00:01:00Z' }]
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: snapshots[0], meta }) })
    }
    if (url.includes(`/systems/${systemId}/context-snapshots`)) return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { items: snapshots }, meta }) })
    if (url.includes(`/systems/${systemId}/sources`)) return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { items: [source] }, meta }) })
    if (url.endsWith(`/systems/${systemId}`)) return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: system, meta }) })
    if (url.includes('/system-context/systems')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { items: [system] }, meta }) })
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { service: 'holospan-api', version: '0.1.0', deploymentMode: 'docker-compose', capabilities: [] }, meta }) })
  })
  vi.stubGlobal('fetch', fetchMock)

  renderApp()
  await screen.findByRole('heading', { name: /prove what your agents can safely do/i })
  fireEvent.click(screen.getByRole('button', { name: 'Systems' }))
  fireEvent.click(await screen.findByRole('button', { name: /open travel agent/i }))
  fireEvent.click(await screen.findByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: /discover context/i }))

  expect(await screen.findByRole('heading', { name: /review discovered capabilities/i })).toBeInTheDocument()
  expect(screen.getAllByText('Search hotels by destination and budget.')).not.toHaveLength(0)
  fireEvent.change(screen.getByLabelText('Review comment'), { target: { value: 'Matches the approved product requirements.' } })
  fireEvent.click(screen.getByRole('button', { name: /approve context/i }))

  expect(await screen.findByText('approved')).toBeInTheDocument()
})

it('moves to sign-in as soon as the server-reported session has expired', async () => {
  const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    if (url.endsWith('/oidc-config')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { enabled: true }, meta }) })
    }
    if (url.endsWith('/session')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          data: {
            principal: { id: '019aca05-8233-7cc1-b2cc-9727fc367b6d', email: 'user@example.com', displayName: 'Test User', status: 'active' },
            memberships: [],
            platformRoles: [],
            platformPermissions: [],
            csrfToken: 'expired-csrf-token',
            expiresAt: '2000-01-01T00:00:00Z',
          },
          meta,
        }),
      })
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { service: 'holospan-api', version: '0.1.0', deploymentMode: 'docker-compose', capabilities: [] }, meta }) })
  })
  vi.stubGlobal('fetch', fetchMock)

  renderApp()

  expect(await screen.findByRole('heading', { name: /your session expired/i })).toBeInTheDocument()
  expect(screen.queryByText('Test User')).not.toBeInTheDocument()
})

it('locks the workspace when a protected API reports that the session is no longer valid', async () => {
  const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    if (url.endsWith('/oidc-config')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { enabled: true }, meta }) })
    }
    if (url.endsWith('/session')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          data: {
            principal: { id: '019aca05-8233-7cc1-b2cc-9727fc367b6d', email: 'user@example.com', displayName: 'Test User', status: 'active' },
            memberships: [],
            platformRoles: [],
            platformPermissions: [],
            csrfToken: 'csrf-test-token',
            expiresAt: '2999-11-22T01:00:00Z',
          },
          meta,
        }),
      })
    }
    return Promise.resolve({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ error: { code: 'AUTHENTICATION_REQUIRED', message: 'Authentication is required.' } }),
    })
  })
  vi.stubGlobal('fetch', fetchMock)

  renderApp()

  expect(await screen.findByRole('heading', { name: /your session expired/i })).toBeInTheDocument()
})

it('signs out locally and follows the identity-provider logout redirect', async () => {
  const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    if (url.endsWith('/oidc-config')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { enabled: true }, meta }) })
    }
    if (url.endsWith('/session') && init?.method === 'DELETE') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { redirectUri: '#signed-out' }, meta }) })
    }
    if (url.endsWith('/session')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          data: {
            principal: { id: '019aca05-8233-7cc1-b2cc-9727fc367b6d', email: 'user@example.com', displayName: 'Test User', status: 'active' },
            memberships: [],
            platformRoles: [],
            platformPermissions: [],
            csrfToken: 'csrf-test-token',
            expiresAt: '2999-11-22T01:00:00Z',
          },
          meta,
        }),
      })
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ data: { service: 'holospan-api', version: '0.1.0', deploymentMode: 'docker-compose', capabilities: [] }, meta }) })
  })
  vi.stubGlobal('fetch', fetchMock)

  renderApp()
  fireEvent.click(await screen.findByRole('button', { name: /sign out/i }))

  await waitFor(() => expect(window.location.hash).toBe('#signed-out'))
  expect(fetchMock).toHaveBeenCalledWith(
    '/api/v1/identity-access/session',
    expect.objectContaining({ method: 'DELETE', credentials: 'same-origin' }),
  )
})
