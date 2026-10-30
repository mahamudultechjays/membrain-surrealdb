import { render, screen } from '@testing-library/react'
import HealthStatus from '@/components/HealthStatus'

const HEALTHY_API = {
  status: 200,
  body: { status: 'ok', version: '0.1.0', environment: 'development' },
}

function mockFetch(responses: Record<string, { status: number; body: unknown }>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = input.toString()
      const match = Object.entries(responses).find(([path]) => url.endsWith(path))
      if (!match) throw new Error(`Unexpected fetch: ${url}`)
      const [, { status, body }] = match
      return new Response(JSON.stringify(body), { status })
    }),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('HealthStatus', () => {
  it('shows the API version and a reachable Agent Memory', async () => {
    mockFetch({
      '/api/v1/health': HEALTHY_API,
      '/api/v1/health/ready': { status: 200, body: { status: 'ok', agent_memory: 'ok' } },
    })

    render(<HealthStatus />)

    expect(await screen.findByText('ok (v0.1.0, development)')).toBeInTheDocument()
    expect(await screen.findByText('ok')).toBeInTheDocument()
  })

  it('tells the user to configure Agent Memory when settings are missing', async () => {
    mockFetch({
      '/api/v1/health': HEALTHY_API,
      '/api/v1/health/ready': {
        status: 503,
        body: { status: 'unavailable', agent_memory: 'not_configured' },
      },
    })

    render(<HealthStatus />)

    expect(
      await screen.findByText('not configured (set AGENT_MEMORY_* in .env)'),
    ).toBeInTheDocument()
  })

  it('reports Agent Memory as unavailable when the service fails', async () => {
    mockFetch({
      '/api/v1/health': HEALTHY_API,
      '/api/v1/health/ready': {
        status: 503,
        body: { status: 'unavailable', agent_memory: 'unavailable' },
      },
    })

    render(<HealthStatus />)

    expect(await screen.findByText('unavailable')).toBeInTheDocument()
  })
})
