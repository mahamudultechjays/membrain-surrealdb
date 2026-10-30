import { render, screen } from '@testing-library/react'
import HealthStatus from '@/components/HealthStatus'

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
  it('shows the API version and a healthy database', async () => {
    mockFetch({
      '/api/v1/health': {
        status: 200,
        body: { status: 'ok', version: '0.1.0', environment: 'development' },
      },
      '/api/v1/health/ready': { status: 200, body: { status: 'ok', database: 'ok' } },
    })

    render(<HealthStatus />)

    expect(await screen.findByText('ok (v0.1.0, development)')).toBeInTheDocument()
    expect(await screen.findByText('ok')).toBeInTheDocument()
  })

  it('reports the database as unavailable when readiness returns 503', async () => {
    mockFetch({
      '/api/v1/health': {
        status: 200,
        body: { status: 'ok', version: '0.1.0', environment: 'development' },
      },
      '/api/v1/health/ready': {
        status: 503,
        body: { status: 'unavailable', database: 'unavailable' },
      },
    })

    render(<HealthStatus />)

    expect(await screen.findByText('unavailable')).toBeInTheDocument()
  })
})
