import { fireEvent, render, screen } from '@testing-library/react'
import type { Me } from '@/api/auth'
import Login from '@/components/Login'

const ME: Me = {
  email: 'priya.shah@x.com',
  name: 'Priya Shah',
  is_admin: false,
  grants: [
    { scope_path: 'org/spreetail/user/priya_shah', access: 'write', layer: 'personal' },
  ],
}

function mockFetch(config: { sso_enabled: boolean; dev_login_enabled: boolean }) {
  const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
    const url = input.toString()
    if (url.endsWith('/api/v1/auth/config')) return new Response(JSON.stringify(config))
    if (url.endsWith('/api/v1/auth/dev-login') && init?.method === 'POST') {
      return new Response(JSON.stringify(ME))
    }
    throw new Error(`Unexpected fetch: ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Login', () => {
  it('offers SSO when the backend has it configured', async () => {
    mockFetch({ sso_enabled: true, dev_login_enabled: false })

    render(<Login onSignedIn={vi.fn<(me: Me) => void>()} />)

    expect(
      await screen.findByRole('button', { name: 'Login with SSO' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('form', { name: 'Developer sign-in' }),
    ).not.toBeInTheDocument()
  })

  it('signs in by email when only the dev login is on', async () => {
    const fetchMock = mockFetch({ sso_enabled: false, dev_login_enabled: true })
    const onSignedIn = vi.fn<(me: Me) => void>()

    render(<Login onSignedIn={onSignedIn} />)
    fireEvent.change(await screen.findByLabelText('Email'), {
      target: { value: 'priya.shah@x.com' },
    })
    fireEvent.change(screen.getByLabelText('Full name'), {
      target: { value: 'Priya Shah' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await vi.waitFor(() => expect(onSignedIn).toHaveBeenCalledWith(ME))
    const [, init] = fetchMock.mock.calls.find(([url]) =>
      url.toString().endsWith('dev-login'),
    )!
    expect(JSON.parse(init!.body as string)).toEqual({
      email: 'priya.shah@x.com',
      name: 'Priya Shah',
    })
  })
})
