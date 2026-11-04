import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { AdminApi, UserGrants } from '@/api/admin'
import type { Me } from '@/api/auth'
import AdminPage from '@/pages/AdminPage'

// The memory jobs at the bottom of the page has its own tests; keep it quiet here.
vi.mock('@/api/lab', async (original) => ({
  ...(await original<typeof import('@/api/lab')>()),
  labApi: {
    scopes: () => Promise.resolve([]),
    run: () => Promise.reject(new Error('not in these tests')),
  },
}))

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
  {
    email: 'ravi@spreetail.com',
    name: 'Ravi Menon',
    is_admin: false,
    grants: [
      { scope_path: ROOT, access: 'read', layer: 'org' },
      { scope_path: `${ROOT}/team/ops`, access: 'read', layer: 'team' },
      { scope_path: `${ROOT}/team`, access: 'read', layer: 'team' },
      { scope_path: `${ROOT}/team/qa`, access: 'read', layer: 'team' },
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
  screen.getByRole('cell', { name: new RegExp(`^${name}`) }).closest('tbody')!

/** Renders the page and waits for the users and the registered scopes. */
async function renderPage(api: AdminApi) {
  render(<AdminPage me={ME} api={api} />)
  await screen.findAllByText('not in Agent Memory')
}

/** Opens the grant dialog from a user's row. */
function addScopeFor(name: string) {
  fireEvent.click(
    within(row(name)).getByRole('button', { name: `Add a scope for ${name}` }),
  )
  return within(screen.getByRole('dialog', { name: `Add a scope for ${name}` }))
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
    // Grants and new scopes live in dialogs, not in forms under the table.
    expect(screen.queryByRole('form')).not.toBeInTheDocument()
  })

  it('shows two scopes per person until the arrow or "Show more" opens the rest', async () => {
    await renderPage(fakeApi())
    const ravi = row('Ravi Menon')
    const scopes = () =>
      within(ravi)
        .getAllByRole('cell')
        .filter((cell) => cell.classList.contains('admin-scope'))
        .map((cell) => cell.querySelector('.admin-path')?.textContent)

    expect(scopes()).toEqual([ROOT, `${ROOT}/team/ops`])
    // The hidden team/qa scope isn't registered; its warning stays in sight.
    expect(within(ravi).getByText('1 not in Agent Memory')).toBeInTheDocument()
    const arrow = within(ravi).getByRole('button', {
      name: 'Show all 4 scopes for Ravi Menon',
    })
    expect(arrow).toHaveAttribute('aria-expanded', 'false')

    fireEvent.click(within(ravi).getByRole('button', { name: 'Show 2 more scopes' }))
    expect(scopes()).toHaveLength(4)
    expect(arrow).toHaveAttribute('aria-expanded', 'true')
    expect(within(ravi).getByText('not in Agent Memory')).toBeInTheDocument()

    fireEvent.click(arrow)
    expect(scopes()).toHaveLength(2)
    expect(
      within(ravi).getByRole('button', { name: 'Show 2 more scopes' }),
    ).toHaveAttribute('aria-expanded', 'false')
    // Two scopes or fewer: nothing to open.
    expect(
      within(row('Arun Das')).queryByRole('button', { name: /^Show/ }),
    ).not.toBeInTheDocument()
  })

  it("grants an existing scope from the person's row without typing their email", async () => {
    const api = fakeApi()
    await renderPage(api)

    const dialog = addScopeFor('Arun Das')
    expect(dialog.queryByLabelText('Email')).not.toBeInTheDocument()
    expect(dialog.getByText('arun@spreetail.com')).toBeInTheDocument()
    expect(dialog.getByLabelText('Scope')).toHaveFocus()
    fireEvent.change(dialog.getByLabelText('Scope'), {
      target: { value: `${ROOT}/team/ops/` },
    })
    fireEvent.click(dialog.getByRole('button', { name: 'Grant' }))

    await screen.findByText(`Granted read on ${ROOT}/team/ops to Arun Das.`)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(api.grant).toHaveBeenCalledWith('arun@spreetail.com', {
      scope_path: `${ROOT}/team/ops`,
      access: 'read',
      layer: 'team',
      name: null,
    })
  })

  it('says when the person already holds the scope', async () => {
    await renderPage(fakeApi())

    const dialog = addScopeFor('Arun Das')
    fireEvent.change(dialog.getByLabelText('Scope'), {
      target: { value: `${ROOT}/team/gone` },
    })

    expect(dialog.getByText(/Arun Das already holds this scope/)).toBeInTheDocument()
  })

  it('asks before a grant creates scopes, listing parents first', async () => {
    const api = fakeApi()
    await renderPage(api)

    const dialog = addScopeFor('Arun Das')
    fireEvent.change(dialog.getByLabelText('Scope'), {
      target: { value: `${ROOT}/team/qa/core` },
    })
    fireEvent.click(dialog.getByRole('button', { name: 'Grant' }))

    const confirm = dialog.getByRole('region', { name: 'Create scopes in Agent Memory' })
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

  it('adds a person who has not signed in yet, asking for their name', async () => {
    const api = fakeApi()
    await renderPage(api)

    fireEvent.click(screen.getByRole('button', { name: 'Add person or grant access' }))
    const dialog = within(
      screen.getByRole('dialog', { name: 'Add person or grant access' }),
    )
    fireEvent.change(dialog.getByLabelText('Email'), {
      target: { value: 'vidyul@spreetail.com' },
    })
    fireEvent.change(dialog.getByLabelText(/^Name/), {
      target: { value: 'Vidyul Narayanan' },
    })
    fireEvent.change(dialog.getByLabelText('Scope'), {
      target: { value: `${ROOT}/team/ops` },
    })
    fireEvent.click(dialog.getByRole('button', { name: 'Grant' }))

    await screen.findByText(`Granted read on ${ROOT}/team/ops to Vidyul Narayanan.`)
    expect(api.grant).toHaveBeenCalledWith(
      'vidyul@spreetail.com',
      expect.objectContaining({ name: 'Vidyul Narayanan' }),
    )
  })

  it('treats an email already in the list as adding a scope to that person', async () => {
    await renderPage(fakeApi())

    fireEvent.click(screen.getByRole('button', { name: 'Add person or grant access' }))
    const dialog = within(
      screen.getByRole('dialog', { name: 'Add person or grant access' }),
    )
    fireEvent.change(dialog.getByLabelText('Email'), {
      target: { value: 'Arun@Spreetail.com' },
    })

    expect(dialog.getByText(/Arun Das is already in the list/)).toBeInTheDocument()
    expect(dialog.queryByLabelText(/^Name/)).not.toBeInTheDocument()
    // Arun already has a personal scope, so picking Personal needs no warning.
    fireEvent.change(dialog.getByLabelText('Layer'), { target: { value: 'personal' } })
    expect(dialog.queryByText(/won't get their own/)).not.toBeInTheDocument()
  })

  it('warns that a Personal grant replaces the personal scope a new person would get', async () => {
    await renderPage(fakeApi())

    fireEvent.click(screen.getByRole('button', { name: 'Add person or grant access' }))
    const dialog = within(
      screen.getByRole('dialog', { name: 'Add person or grant access' }),
    )
    fireEvent.change(dialog.getByLabelText('Email'), {
      target: { value: 'vidyul@spreetail.com' },
    })
    expect(dialog.queryByText(/won't get their own/)).not.toBeInTheDocument()
    fireEvent.change(dialog.getByLabelText('Layer'), { target: { value: 'personal' } })

    expect(dialog.getByText(/won't get their own/)).toBeInTheDocument()
  })

  it('closes a dialog on Escape and gives focus back to its button', async () => {
    await renderPage(fakeApi())
    const opener = screen.getByRole('button', { name: 'New scope' })
    opener.focus()

    fireEvent.click(opener)
    expect(screen.getByRole('dialog', { name: 'New scope' })).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(opener).toHaveFocus()
  })

  it('asks in a popup before revoking, then revokes', async () => {
    const api = fakeApi()
    render(<AdminPage me={ME} api={api} />)
    const arun = await waitFor(() => row('Arun Das'))
    const revokeButton = () =>
      within(arun).getByRole('button', {
        name: `Revoke ${ROOT}/team/gone from Arun Das…`,
      })

    // Cancel leaves the grant alone.
    fireEvent.click(revokeButton())
    let dialog = within(screen.getByRole('dialog', { name: 'Revoke scope access?' }))
    expect(dialog.getByText(`${ROOT}/team/gone`)).toBeInTheDocument()
    fireEvent.click(dialog.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(api.revoke).not.toHaveBeenCalled()

    fireEvent.click(revokeButton())
    dialog = within(screen.getByRole('dialog', { name: 'Revoke scope access?' }))
    fireEvent.click(
      dialog.getByRole('button', { name: `Revoke ${ROOT}/team/gone from Arun Das` }),
    )

    await screen.findByText(/Revoked org\/spreetail\/team\/gone from Arun Das/)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(api.revoke).toHaveBeenCalledWith('arun@spreetail.com', `${ROOT}/team/gone`)
  })

  it('registers a new scope from the header button', async () => {
    const api = fakeApi()
    await renderPage(api)

    fireEvent.click(screen.getByRole('button', { name: 'New scope' }))
    const dialog = within(screen.getByRole('dialog', { name: 'New scope' }))
    fireEvent.change(dialog.getByLabelText('Scope path'), {
      target: { value: `${ROOT}/team/eng` },
    })
    fireEvent.click(dialog.getByRole('button', { name: 'Register scope' }))

    await screen.findByText(`Registered ${ROOT}/team/eng.`)
    expect(api.registerScope).toHaveBeenCalledWith(`${ROOT}/team/eng`)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('does not register a scope that already exists', async () => {
    const api = fakeApi()
    await renderPage(api)

    fireEvent.click(screen.getByRole('button', { name: 'New scope' }))
    const dialog = within(screen.getByRole('dialog', { name: 'New scope' }))
    fireEvent.change(dialog.getByLabelText('Scope path'), {
      target: { value: `${ROOT}/team/ops` },
    })
    fireEvent.click(dialog.getByRole('button', { name: 'Register scope' }))

    expect(await dialog.findByRole('alert')).toHaveTextContent('already registered')
    expect(api.registerScope).not.toHaveBeenCalled()
  })
})
