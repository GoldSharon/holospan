import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import App from './App'

const meta = { requestId: 'test-request', timestamp: '2026-11-22T00:00:00Z' }

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><App /></QueryClientProvider>)
}

afterEach(() => {
  vi.unstubAllGlobals()
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
          platformRoles: [], platformPermissions: [], csrfToken: 'csrf-test-token',
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
