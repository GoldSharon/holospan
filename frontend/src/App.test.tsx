import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import App from './App'

const response = {
  data: {
    service: 'holospan-api',
    version: '0.1.0',
    deploymentMode: 'docker-compose',
    capabilities: [
      { id: 'health', name: 'Health checks', status: 'available', description: 'Operational probes' },
    ],
  },
  meta: { requestId: 'test-request', timestamp: '2026-11-22T00:00:00Z' },
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(response) }))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

it('renders the assurance workspace and connects to the API contract', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>)

  expect(screen.getByRole('heading', { name: /prove what your agents can safely do/i })).toBeInTheDocument()
  expect(await screen.findByText('API connected')).toBeInTheDocument()
  expect(screen.getByText('First assurance loop')).toBeInTheDocument()
})
