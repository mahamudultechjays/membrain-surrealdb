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
  `${ROOT}/lab`,
  `${ROOT}/lab/probe`,
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

  /** An api whose registry grows as scopes are registered. */
  function growingApi() {
    const paths = [...REGISTERED]
    return fakeApi({
      scopes: vi.fn<AdminApi['scopes']>(async () => [...paths]),
      registerScope: vi.fn<AdminApi['registerScope']>(async (path) => {
        paths.push(path)
      }),
    })
  }

  async function openNewScope(api: AdminApi) {
    await renderPage(api)
    fireEvent.click(screen.getByRole('button', { name: 'New scope' }))
    return within(screen.getByRole('dialog', { name: 'New scope' }))
  }

  it('creates a team scope from just a name, under the fixed team prefix', async () => {
    const api = growingApi()
    const dialog = await openNewScope(api)

    // Org has no "+"; other areas under it are listed, read-only.
    const org = within(dialog.getByRole('region', { name: 'Org' }))
    expect(org.queryByRole('button', { name: /^Add/ })).not.toBeInTheDocument()
    expect(org.getByText('lab')).toBeInTheDocument()
    expect(org.getByText('lab').closest('li')).toHaveTextContent(/^lab1 sub-scope$/)

    const team = within(dialog.getByRole('region', { name: 'Team' }))
    expect(team.getByText('ops')).toBeInTheDocument()
    fireEvent.click(team.getByRole('button', { name: 'Add a team scope' }))
    const name = team.getByLabelText('Team name')
    expect(name).toHaveFocus()
    fireEvent.change(name, { target: { value: 'Customer Support' } })
    expect(name).toHaveAccessibleDescription(
      expect.stringContaining(`Creates ${ROOT}/team/customer-support`),
    )
    fireEvent.click(team.getByRole('button', { name: 'Create' }))

    // The dialog stays open, with the new scope in its column.
    expect(await dialog.findByRole('status')).toHaveTextContent(
      `Created ${ROOT}/team/customer-support.`,
    )
    expect(api.registerScope).toHaveBeenCalledWith(`${ROOT}/team/customer-support`)
    const item = (await team.findByText('customer-support')).closest('li')!
    expect(within(item).getByText('new')).toBeInTheDocument()
    expect(team.queryByLabelText('Team name')).not.toBeInTheDocument()
    expect(team.getByRole('button', { name: 'Add a team scope' })).toHaveFocus()
  })

  it('names an individual scope as sign-in would, and refuses one that exists', async () => {
    const api = growingApi()
    const dialog = await openNewScope(api)
    const person = within(dialog.getByRole('region', { name: 'Individual' }))

    fireEvent.click(person.getByRole('button', { name: 'Add an individual scope' }))
    const name = person.getByLabelText("Person's name")
    fireEvent.change(name, { target: { value: 'Priya Nair' } })
    expect(person.getByText('That scope already exists.')).toBeInTheDocument()
    expect(person.getByRole('button', { name: 'Create' })).toBeDisabled()

    fireEvent.change(name, { target: { value: 'Ravi Kumar Menon' } })
    expect(name).toHaveAccessibleDescription(
      expect.stringContaining(`Creates ${ROOT}/user/ravi_menon`),
    )

    // Escape closes the field, not the dialog.
    fireEvent.keyDown(name, { key: 'Escape' })
    expect(person.queryByLabelText("Person's name")).not.toBeInTheDocument()
    expect(screen.getByRole('dialog', { name: 'New scope' })).toBeInTheDocument()
    expect(api.registerScope).not.toHaveBeenCalled()
  })

  it('adds a sub-scope inside a picked team, asking only for the rest of the path', async () => {
    const api = growingApi()
    const dialog = await openNewScope(api)
    const team = within(dialog.getByRole('region', { name: 'Team' }))
    const ops = team.getByRole('button', { name: 'ops: add a sub-scope inside' })

    fireEvent.click(ops)
    expect(ops).toHaveAttribute('aria-pressed', 'true')
    const name = team.getByLabelText('Sub-scope in ops')
    expect(name).toHaveFocus()
    // Picking alone creates nothing: a name is still needed.
    expect(team.getByRole('button', { name: 'Create' })).toBeDisabled()

    fireEvent.change(name, { target: { value: 'Supplier Calls' } })
    expect(name).toHaveAccessibleDescription(
      expect.stringContaining(`Creates ${ROOT}/team/ops/supplier-calls`),
    )
    fireEvent.click(team.getByRole('button', { name: 'Create' }))

    expect(await dialog.findByRole('status')).toHaveTextContent(
      `Created ${ROOT}/team/ops/supplier-calls.`,
    )
    expect(api.registerScope).toHaveBeenCalledWith(`${ROOT}/team/ops/supplier-calls`)
    // ops now shows what is inside it, the new scope marked, and focus is back on ops.
    const opsRow = team.getByRole('button', { name: 'ops: add a sub-scope inside' })
    expect(opsRow).toHaveFocus()
    expect(opsRow).toHaveTextContent(/^ops1 sub-scope$/)
    expect(team.getByRole('button', { name: "Hide what's inside ops" })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
    const added = team.getByRole('button', {
      name: 'supplier-calls: add a sub-scope inside',
    })
    expect(within(added).getByText('new')).toBeInTheDocument()

    // The new sub-scope can itself be opened, to go a level deeper.
    fireEvent.click(added)
    expect(team.getByLabelText('Sub-scope in ops/supplier-calls')).toHaveFocus()

    // "+" goes back to a new team at the top level.
    fireEvent.click(team.getByRole('button', { name: 'Add a team scope' }))
    expect(team.getByLabelText('Team name')).toBeInTheDocument()
    expect(added).toHaveAttribute('aria-pressed', 'false')
  })

  it('offers to grant the scope it just made, filled in', async () => {
    const dialog = await openNewScope(growingApi())
    const team = within(dialog.getByRole('region', { name: 'Team' }))
    fireEvent.click(team.getByRole('button', { name: 'Add a team scope' }))
    fireEvent.change(team.getByLabelText('Team name'), { target: { value: 'eng' } })
    fireEvent.click(team.getByRole('button', { name: 'Create' }))
    fireEvent.click(await dialog.findByRole('button', { name: 'Grant access…' }))

    const grant = within(
      screen.getByRole('dialog', { name: 'Add person or grant access' }),
    )
    expect(grant.getByLabelText('Scope')).toHaveValue(`${ROOT}/team/eng`)
    expect(grant.getByLabelText('Layer')).toHaveValue('team')
    expect(grant.getByLabelText('Email')).toHaveFocus()
  })
})

describe('AdminPage sections', () => {
  afterEach(() => {
    window.location.hash = ''
  })

  it('opens on Access, with tabs linking to #/admin/access and #/admin/lab', async () => {
    await renderPage(fakeApi())

    const tabs = screen.getByRole('navigation', { name: 'Admin section' })
    const access = within(tabs).getByRole('link', { name: 'Access' })
    expect(access).toHaveAttribute('aria-current', 'page')
    expect(access).toHaveAttribute('href', '#/admin/access')
    expect(within(tabs).getByRole('link', { name: 'Lab' })).toHaveAttribute(
      'href',
      '#/admin/lab',
    )
    expect(screen.getByRole('button', { name: 'New scope' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'Memory jobs' })).not.toBeInTheDocument()
  })

  it('#/admin/lab shows the memory jobs and not the access tools', async () => {
    window.location.hash = '#/admin/lab'

    render(<AdminPage me={ME} api={fakeApi()} />)

    expect(await screen.findByRole('heading', { name: 'Memory jobs' })).toBeVisible()
    expect(screen.queryByRole('button', { name: 'New scope' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Lab' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })
})
