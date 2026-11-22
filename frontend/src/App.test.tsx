import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
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
  expect(screen.getByText('OIDC configuration required')).toBeInTheDocument()
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
  expect(await screen.findByText('API connected')).toBeInTheDocument()
  expect(screen.getByLabelText('Current workspace')).toHaveValue('019aca05-8233-7cc1-b2cc-9727fc367b6f')
  expect(screen.getByText('Test User')).toBeInTheDocument()
})
