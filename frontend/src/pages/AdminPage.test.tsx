import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { AdminApi, UserGrants } from '@/api/admin'
import type { Me } from '@/api/auth'
import AdminPage from '@/pages/AdminPage'

const ROOT = 'org/spreetail'
const ME: Me = {
  email: 'priya@spreetail.com',
  name: 'Priya Nair',
  is_admin: true,
  grants: [],
}

const USERS: UserGrants[] = [
  {
    email: ME.email,
    name: ME.name,
    is_admin: true,
    grants: [
      { scope_path: ROOT, access: 'read', layer: 'org' },
      { scope_path: `${ROOT}/user/priya_nair`, access: 'write', layer: 'personal' },
    ],
  },
  {
    email: 'arun@spreetail.com',
    name: 'Arun Das',
    is_admin: false,
    grants: [
      { scope_path: ROOT, access: 'read', layer: 'org' },
      { scope_path: `${ROOT}/team/gone`, access: 'read', layer: 'team' },
    ],
  },
]

const REGISTERED = [
  ROOT,
  `${ROOT}/team`,
  `${ROOT}/team/ops`,
  `${ROOT}/user`,
  `${ROOT}/user/priya_nair`,
]

function fakeApi(overrides: Partial<AdminApi> = {}): AdminApi {
  return {
    users: vi.fn<AdminApi['users']>(async () => USERS),
    grant: vi.fn<AdminApi['grant']>(async () => USERS[1]!),
    revoke: vi.fn<AdminApi['revoke']>(async () => undefined),
    scopes: vi.fn<AdminApi['scopes']>(async () => REGISTERED),
    registerScope: vi.fn<AdminApi['registerScope']>(async () => undefined),
    ...overrides,
  }
}

const row = (name: string) =>
  screen.getByRole('cell', { name: new RegExp(`^${name}`) }).closest('tr')!

const grantForm = () => screen.getByRole('form', { name: 'Grant a scope' })

function fillGrant(email: string, scope: string) {
  const form = within(grantForm())
  fireEvent.change(form.getByLabelText('Person'), { target: { value: email } })
  fireEvent.change(form.getByLabelText('Scope'), { target: { value: scope } })
}

describe('AdminPage', () => {
  it('lists each user with their grants and flags a scope missing from Agent Memory', async () => {
    render(<AdminPage me={ME} api={fakeApi()} />)

    const priya = await waitFor(() => row('Priya Nair'))
    expect(within(priya).getByText('you')).toBeInTheDocument()
    expect(within(priya).getByText('read & write')).toBeInTheDocument()
    const arun = row('Arun Das')
    expect(await within(arun).findByText('not in Agent Memory')).toBeInTheDocument()
    expect(within(priya).queryByText('not in Agent Memory')).not.toBeInTheDocument()
  })

  it('grants an existing scope straight away', async () => {
    const api = fakeApi()
    render(<AdminPage me={ME} api={api} />)
    await screen.findByText('Arun Das')
    await waitFor(() => expect(api.scopes).toHaveBeenCalled())

    fillGrant('Arun@Spreetail.com', `${ROOT}/team/ops/`)
    fireEvent.click(within(grantForm()).getByRole('button', { name: 'Grant' }))

    await screen.findByText(`Granted read on ${ROOT}/team/ops to Arun Das.`)
    expect(api.grant).toHaveBeenCalledWith('arun@spreetail.com', {
      scope_path: `${ROOT}/team/ops`,
      access: 'read',
      layer: 'team',
      name: null,
    })
  })

  it('asks before a grant creates scopes, listing parents first', async () => {
    const api = fakeApi()
    render(<AdminPage me={ME} api={api} />)
    await screen.findByText('Arun Das')
    await screen.findAllByText('not in Agent Memory')

    fillGrant('arun@spreetail.com', `${ROOT}/team/qa/core`)
    fireEvent.click(within(grantForm()).getByRole('button', { name: 'Grant' }))

    const confirm = screen.getByRole('region', { name: 'Create scopes in Agent Memory' })
    expect(
      within(confirm)
        .getAllByRole('listitem')
        .map((li) => li.textContent),
    ).toEqual([`${ROOT}/team/qa`, `${ROOT}/team/qa/core`])
    expect(api.grant).not.toHaveBeenCalled()

    fireEvent.click(
      within(confirm).getByRole('button', { name: 'Create 2 scopes and grant' }),
    )
    await waitFor(() => expect(api.grant).toHaveBeenCalledTimes(1))
  })

  it('asks for a name when granting someone who has not signed in yet', async () => {
    const api = fakeApi()
    render(<AdminPage me={ME} api={api} />)
    await screen.findByText('Arun Das')
    await screen.findAllByText('not in Agent Memory')

    fillGrant('vidyul@spreetail.com', `${ROOT}/team/ops`)
    fireEvent.change(within(grantForm()).getByLabelText(/^Name/), {
      target: { value: 'Vidyul Kumar' },
    })
    fireEvent.click(within(grantForm()).getByRole('button', { name: 'Grant' }))

    await waitFor(() =>
      expect(api.grant).toHaveBeenCalledWith(
        'vidyul@spreetail.com',
        expect.objectContaining({ name: 'Vidyul Kumar' }),
      ),
    )
  })

  it('asks before revoking, then revokes', async () => {
    const api = fakeApi()
    render(<AdminPage me={ME} api={api} />)
    const arun = await waitFor(() => row('Arun Das'))

    fireEvent.click(
      within(arun).getByRole('button', {
        name: `Revoke ${ROOT}/team/gone from Arun Das…`,
      }),
    )
    expect(api.revoke).not.toHaveBeenCalled()
    fireEvent.click(
      within(arun).getByRole('button', {
        name: `Revoke ${ROOT}/team/gone from Arun Das`,
      }),
    )

    await screen.findByText(/Revoked org\/spreetail\/team\/gone from Arun Das/)
    expect(api.revoke).toHaveBeenCalledWith('arun@spreetail.com', `${ROOT}/team/gone`)
  })

  it('does not register a scope that already exists', async () => {
    const api = fakeApi()
    render(<AdminPage me={ME} api={api} />)
    await screen.findAllByText('not in Agent Memory')

    const form = within(screen.getByRole('form', { name: 'Register a scope' }))
    fireEvent.change(form.getByLabelText('Scope path'), {
      target: { value: `${ROOT}/team/ops` },
    })
    fireEvent.click(form.getByRole('button', { name: 'Register scope' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('already registered')
    expect(api.registerScope).not.toHaveBeenCalled()
  })
})
