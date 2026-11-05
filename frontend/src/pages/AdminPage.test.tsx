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
    memory_grants: { 'memory:read': ['/org/spreetail/*'], 'scope:read': ['/*'] },
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
  // Known to Agent Memory only: no scopes in this app yet.
  {
    email: 'stephen.howard@spreetail.com',
    name: 'Stephen Howard',
    is_admin: false,
    grants: [],
    memory_grants: {
      'memory:read': ['/*'],
      'memory:write': ['/*'],
      'memory:forget': ['/*'],
      'scope:read': ['/*'],
      'scope:create': ['/*'],
      'scope:delete': ['/*'],
      'grant:manage': ['/*'],
    },
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
    users: vi.fn<AdminApi['users']>(async () => ({ users: USERS, people_error: null })),
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
      name: 'Show all 5 scopes for Ravi Menon',
    })
    expect(arrow).toHaveAttribute('aria-expanded', 'false')

    fireEvent.click(within(ravi).getByRole('button', { name: 'Show 3 more scopes' }))
    expect(scopes()).toHaveLength(4)
    expect(arrow).toHaveAttribute('aria-expanded', 'true')
    expect(within(ravi).getByText('not in Agent Memory')).toBeInTheDocument()

    fireEvent.click(arrow)
    expect(scopes()).toHaveLength(2)
    expect(
      within(ravi).getByRole('button', { name: 'Show 3 more scopes' }),
    ).toHaveAttribute('aria-expanded', 'false')
    // Two lines or fewer (Stephen: none here, one in Agent Memory): nothing to open.
    expect(
      within(row('Stephen Howard')).queryByRole('button', { name: /^Show/ }),
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

  it('types a scope path in lower case with "_" for spaces, and fixes other symbols', async () => {
    const api = fakeApi()
    await renderPage(api)

    const dialog = addScopeFor('Arun Das')
    const scope = dialog.getByLabelText('Scope')
    fireEvent.change(scope, { target: { value: 'Org/Spreetail/Team Ops' } })
    expect(scope).toHaveValue('org/spreetail/team_ops')
    expect(scope).not.toHaveAttribute('aria-invalid')

    fireEvent.change(scope, { target: { value: 'org/spreetail/team&ops' } })
    expect(scope).toHaveAttribute('aria-invalid', 'true')
    expect(scope).toHaveAccessibleDescription(expect.stringContaining('Remove “&”'))
    expect(dialog.getByRole('button', { name: 'Grant' })).toBeDisabled()

    fireEvent.click(dialog.getByRole('button', { name: 'Use org/spreetail/team_ops' }))
    expect(scope).toHaveValue('org/spreetail/team_ops')
    expect(dialog.getByRole('button', { name: 'Grant' })).toBeEnabled()
    expect(api.grant).not.toHaveBeenCalled()
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

  it('lists people only Agent Memory knows, with no scopes yet, and no "Add person"', async () => {
    await renderPage(fakeApi())

    const stephen = row('Stephen Howard')
    expect(within(stephen).getByText('No scopes in this app yet')).toBeInTheDocument()
    expect(within(stephen).getByText('stephen.howard@spreetail.com')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Add person/ })).not.toBeInTheDocument()
  })

  it('gives someone with no scopes their first, sending their name along', async () => {
    const api = fakeApi()
    await renderPage(api)

    const dialog = addScopeFor('Stephen Howard')
    fireEvent.change(dialog.getByLabelText('Scope'), {
      target: { value: `${ROOT}/team/ops` },
    })
    fireEvent.click(dialog.getByRole('button', { name: 'Grant' }))

    await screen.findByText(`Granted read on ${ROOT}/team/ops to Stephen Howard.`)
    expect(api.grant).toHaveBeenCalledWith(
      'stephen.howard@spreetail.com',
      expect.objectContaining({ name: 'Stephen Howard' }),
    )
  })

  it('asks no layer: the org root is granted as Org, every other scope as Team', async () => {
    const api = fakeApi()
    await renderPage(api)

    let dialog = addScopeFor('Stephen Howard')
    expect(dialog.queryByLabelText('Layer')).not.toBeInTheDocument()
    fireEvent.change(dialog.getByLabelText('Scope'), { target: { value: ROOT } })
    fireEvent.click(dialog.getByRole('button', { name: 'Grant' }))
    await screen.findByText(`Granted read on ${ROOT} to Stephen Howard.`)
    expect(api.grant).toHaveBeenLastCalledWith(
      'stephen.howard@spreetail.com',
      expect.objectContaining({ scope_path: ROOT, layer: 'org' }),
    )

    dialog = addScopeFor('Stephen Howard')
    fireEvent.change(dialog.getByLabelText('Scope'), {
      target: { value: `${ROOT}/user/priya_nair` },
    })
    fireEvent.click(dialog.getByRole('button', { name: 'Grant' }))
    await waitFor(() =>
      expect(api.grant).toHaveBeenLastCalledWith(
        'stephen.howard@spreetail.com',
        expect.objectContaining({ scope_path: `${ROOT}/user/priya_nair`, layer: 'team' }),
      ),
    )
  })

  it("shows each person's own Agent Memory access as scopes this app can't change", async () => {
    await renderPage(fakeApi())

    // In the Scope column after this app's grants: one row per pattern, not per scope.
    const stephen = within(row('Stephen Howard'))
    const everything = stephen.getByText('every scope').closest('tr')!
    expect(within(everything).getByText('/')).toHaveAttribute('title', '/*')
    expect(within(everything).getByText('Agent Memory')).toBeInTheDocument()
    // Worded like this app's grants; every permission is in the tooltip.
    expect(within(everything).getByText('read & write')).toHaveAttribute(
      'title',
      expect.stringContaining('Manage access'),
    )
    // Where Revoke would be: why it can't be, and no button.
    expect(within(everything).getByText("Can't change here")).toBeInTheDocument()
    expect(within(everything).queryByRole('button')).not.toBeInTheDocument()

    // Arun's two grants come first; his Agent Memory rows are behind "Show more".
    const arun = within(row('Arun Das'))
    expect(arun.queryByText('and every scope inside')).not.toBeInTheDocument()
    fireEvent.click(arun.getByRole('button', { name: 'Show 2 more scopes' }))
    const narrow = arun.getByText('and every scope inside').closest('tr')!
    expect(within(narrow).getByText('org/spreetail')).toHaveAttribute(
      'title',
      '/org/spreetail/*',
    )
    expect(within(narrow).getByText('read')).toBeInTheDocument()

    // Priya signs in here, but Agent Memory has no account with her email.
    fireEvent.click(
      within(row('Priya Nair')).getByRole('button', { name: 'Show 1 more scope' }),
    )
    expect(
      within(row('Priya Nair')).getByText('No Agent Memory account with this email'),
    ).toBeInTheDocument()
  })

  it("says when Agent Memory's people could not be loaded", async () => {
    await renderPage(
      fakeApi({
        users: vi.fn<AdminApi['users']>(async () => ({
          users: USERS.slice(0, 3),
          people_error: 'Agent Memory call failed: 403',
        })),
      }),
    )

    expect(
      screen.getByText(
        /Agent Memory's people could not be loaded \(Agent Memory call failed: 403\)/,
      ),
    ).toBeInTheDocument()
    // Unknown is not the same as "no account": nothing is claimed per person.
    expect(screen.queryByText(/No Agent Memory account/)).not.toBeInTheDocument()
    expect(screen.queryByText("Can't change here")).not.toBeInTheDocument()
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
    // Capitals go lower case and spaces become "_" in the field itself.
    fireEvent.change(name, { target: { value: 'Customer Support' } })
    expect(name).toHaveValue('customer_support')
    expect(name).toHaveAccessibleDescription(
      expect.stringContaining(`Creates ${ROOT}/team/customer_support`),
    )
    fireEvent.click(team.getByRole('button', { name: 'Create' }))

    // The dialog stays open, with the new scope in its column.
    expect(await dialog.findByRole('status')).toHaveTextContent(
      `Created ${ROOT}/team/customer_support.`,
    )
    expect(api.registerScope).toHaveBeenCalledWith(`${ROOT}/team/customer_support`)
    const item = (await team.findByText('customer_support')).closest('li')!
    expect(within(item).getByText('new')).toBeInTheDocument()
    expect(team.queryByLabelText('Team name')).not.toBeInTheDocument()
    expect(team.getByRole('button', { name: 'Add a team scope' })).toHaveFocus()
  })

  it('names an individual scope in lower case with "_", and refuses one that exists', async () => {
    const api = growingApi()
    const dialog = await openNewScope(api)
    const person = within(dialog.getByRole('region', { name: 'Individual' }))

    fireEvent.click(person.getByRole('button', { name: 'Add an individual scope' }))
    const name = person.getByLabelText("Person's name")
    fireEvent.change(name, { target: { value: 'PRIYA NAIR' } })
    expect(name).toHaveValue('priya_nair')
    expect(person.getByText('That scope already exists.')).toBeInTheDocument()
    expect(person.getByRole('button', { name: 'Create' })).toBeDisabled()

    fireEvent.change(name, { target: { value: 'Ravi Menon' } })
    expect(name).toHaveAccessibleDescription(
      expect.stringContaining(`Creates ${ROOT}/user/ravi_menon`),
    )

    // Escape closes the field, not the dialog.
    fireEvent.keyDown(name, { key: 'Escape' })
    expect(person.queryByLabelText("Person's name")).not.toBeInTheDocument()
    expect(screen.getByRole('dialog', { name: 'New scope' })).toBeInTheDocument()
    expect(api.registerScope).not.toHaveBeenCalled()
  })

  it('refuses symbols other than "_" in a scope name, with a one-click fix', async () => {
    const api = growingApi()
    const dialog = await openNewScope(api)
    const team = within(dialog.getByRole('region', { name: 'Team' }))
    fireEvent.click(team.getByRole('button', { name: 'Add a team scope' }))
    const name = team.getByLabelText('Team name')

    fireEvent.change(name, { target: { value: 'Ops-Finance' } })
    expect(name).toHaveValue('ops-finance')
    expect(name).toHaveAttribute('aria-invalid', 'true')
    expect(
      team.getByText(/Only lower-case letters, numbers and _ are allowed\. Remove “-”\./),
    ).toBeInTheDocument()
    expect(team.getByRole('button', { name: 'Create' })).toBeDisabled()

    fireEvent.click(team.getByRole('button', { name: 'Use ops_finance' }))
    expect(name).toHaveValue('ops_finance')
    expect(name).not.toHaveAttribute('aria-invalid')
    expect(team.getByRole('button', { name: 'Create' })).toBeEnabled()
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
      expect.stringContaining(`Creates ${ROOT}/team/ops/supplier_calls`),
    )
    fireEvent.click(team.getByRole('button', { name: 'Create' }))

    expect(await dialog.findByRole('status')).toHaveTextContent(
      `Created ${ROOT}/team/ops/supplier_calls.`,
    )
    expect(api.registerScope).toHaveBeenCalledWith(`${ROOT}/team/ops/supplier_calls`)
    // ops now shows what is inside it, the new scope marked, and focus is back on ops.
    const opsRow = team.getByRole('button', { name: 'ops: add a sub-scope inside' })
    expect(opsRow).toHaveFocus()
    expect(opsRow).toHaveTextContent(/^ops1 sub-scope$/)
    expect(team.getByRole('button', { name: "Hide what's inside ops" })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
    const added = team.getByRole('button', {
      name: 'supplier_calls: add a sub-scope inside',
    })
    expect(within(added).getByText('new')).toBeInTheDocument()

    // The new sub-scope can itself be opened, to go a level deeper.
    fireEvent.click(added)
    expect(team.getByLabelText('Sub-scope in ops/supplier_calls')).toHaveFocus()

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

    const grant = within(screen.getByRole('dialog', { name: 'Grant access' }))
    expect(grant.getByLabelText('Scope')).toHaveValue(`${ROOT}/team/eng`)
    // A person is picked from everyone listed; none typed in.
    const person = grant.getByLabelText('Person')
    expect(person).toHaveFocus()
    expect(grant.getByRole('button', { name: 'Grant' })).toBeDisabled()
    expect(
      within(person)
        .getAllByRole('option')
        .map((o) => o.textContent),
    ).toContain('Stephen Howard (stephen.howard@spreetail.com)')
    fireEvent.change(person, { target: { value: 'stephen.howard@spreetail.com' } })
    expect(grant.getByRole('button', { name: 'Grant' })).toBeEnabled()
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
