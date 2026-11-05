import { useEffect, useState, type FormEvent } from 'react'
import { adminApi, type AdminApi, type GrantInput, type UserGrants } from '@/api/admin'
import type { Access, Grant, GrantLayer, Me } from '@/api/auth'
import type { LabApi } from '@/api/lab'
import { cleanPath, unregisteredScopes } from '@/api/scopePaths'
import MemoryLab from '@/components/admin/MemoryLab'
import NewScope from '@/components/admin/NewScope'
import { LAYER_LABELS } from '@/components/ask/layers'
import { isAbort, messageOf } from '@/components/capture/format'
import KeepAlive from '@/components/KeepAlive'
import Modal from '@/components/Modal'
import { useHashSubRoute } from '@/hooks/useHashRoute'
import { useVisited } from '@/hooks/useVisited'
import '@/pages/admin.css'

interface Props {
  me: Me
  api?: AdminApi
  /** The memory jobs' API; defaults to the real (or mock) one. */
  labApi?: LabApi
}

type UsersState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; users: UserGrants[] }

/** The scopes that exist in Agent Memory under the org scope. */
type RegistryState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; paths: ReadonlySet<string> }

/**
 * The open dialog. A grant is either for someone already in the table (their
 * row's "Add scope") or, with `user` null, for a person typed in by email:
 * usually someone who has not signed in yet, so they are not in the table.
 */
type Dialog =
  | { kind: 'scope' }
  /** `prefill`: e.g. the scope just made in New scope. */
  | { kind: 'grant'; user: UserGrants | null; prefill?: Partial<GrantForm> }
  | { kind: 'revoke'; user: UserGrants; grant: Grant }
  | null

interface GrantForm {
  email: string
  name: string
  scope_path: string
  access: Access
  layer: GrantLayer
}

const EMPTY_GRANT: GrantForm = {
  email: '',
  name: '',
  scope_path: '',
  access: 'read',
  layer: 'team',
}
const SCOPE_OPTIONS = 'admin-scope-options'
const USER_OPTIONS = 'admin-user-options'
/** Scopes shown per person before "Show more". */
const VISIBLE_SCOPES = 2

/**
 * Who may read or write which Agent Memory scope. The backend reaches Agent
 * Memory with one admin key, so these grants are the only thing keeping
 * people's memories apart.
 */
function AdminAccess({ me, api = adminApi }: Omit<Props, 'labApi'>) {
  const [users, setUsers] = useState<UsersState>({ status: 'loading' })
  const [registry, setRegistry] = useState<RegistryState>({ status: 'loading' })
  const [dialog, setDialog] = useState<Dialog>(null)
  const [form, setForm] = useState<GrantForm>(EMPTY_GRANT)
  // Scopes the grant would create; set until the admin confirms or goes back.
  const [missing, setMissing] = useState<string[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  // People whose scopes are all shown, by email; others show the first few.
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set())

  const toggleExpanded = (email: string, show?: boolean) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      if (show ?? !next.has(email)) next.add(email)
      else next.delete(email)
      return next
    })

  useEffect(() => {
    const controller = new AbortController()
    api
      .users(controller.signal)
      .then((list) => setUsers({ status: 'ready', users: list }))
      .catch((err: unknown) => {
        if (!isAbort(err)) setUsers({ status: 'error', message: messageOf(err) })
      })
    api
      .scopes(undefined, controller.signal)
      .then((paths) => setRegistry({ status: 'ready', paths: new Set(paths) }))
      .catch((err: unknown) => {
        if (!isAbort(err)) setRegistry({ status: 'error', message: messageOf(err) })
      })
    return () => controller.abort()
  }, [api])

  const list = users.status === 'ready' ? users.users : []
  const known = registry.status === 'ready' ? registry.paths : null
  // The org scope is the shortest path the listing returns.
  const root = known ? [...known].sort((a, b) => a.length - b.length)[0] : undefined
  // Who the open grant dialog is for, when they are already in the table.
  const grantee =
    dialog?.kind === 'grant'
      ? (dialog.user ?? list.find((u) => u.email === form.email.trim().toLowerCase()))
      : undefined
  const alreadyHeld = grantee?.grants.find(
    (g) => g.scope_path === cleanPath(form.scope_path),
  )

  /** Run one change, then reload the users (and scopes, which a grant may add). */
  const run = async (call: () => Promise<unknown>, message: string) => {
    setBusy(true)
    setError(null)
    setDone(null)
    try {
      await call()
      const [fresh, paths] = await Promise.all([api.users(), api.scopes()])
      setUsers({ status: 'ready', users: fresh })
      setRegistry({ status: 'ready', paths: new Set(paths) })
      setDone(message)
      return true
    } catch (err) {
      setError(messageOf(err))
      return false
    } finally {
      setBusy(false)
    }
  }

  const open = (next: Exclude<Dialog, null>) => {
    setError(null)
    setDone(null)
    setMissing(null)
    if (next.kind === 'grant')
      setForm({ ...EMPTY_GRANT, email: next.user?.email ?? '', ...next.prefill })
    setDialog(next)
  }

  const closeDialog = () => {
    setDialog(null)
    setMissing(null)
    setError(null)
  }

  const editForm = (next: GrantForm) => {
    setForm(next)
    setMissing(null)
  }

  const sendGrant = async () => {
    const email = form.email.trim().toLowerCase()
    const name = form.name.trim()
    const grant: GrantInput = {
      scope_path: cleanPath(form.scope_path),
      access: form.access,
      layer: form.layer,
      name: grantee ? null : name || null,
    }
    const ok = await run(
      () => api.grant(email, grant),
      `Granted ${grant.access === 'write' ? 'read and write' : 'read'} on ${grant.scope_path} to ${grantee?.name ?? (name || email)}.`,
    )
    if (ok) {
      // Open their scopes, so the new one is on screen even past the first few.
      toggleExpanded(email, true)
      closeDialog()
    }
  }

  // A grant registers any new path, so a typo would quietly create a scope: ask first.
  const submitGrant = (event: FormEvent) => {
    event.preventDefault()
    const path = cleanPath(form.scope_path)
    const unknown = known && root ? unregisteredScopes([path], known, root) : []
    if (unknown.length) {
      setError(null)
      setMissing(unknown)
      return
    }
    void sendGrant()
  }

  const revoke = async (user: UserGrants, grant: Grant) => {
    const ok = await run(
      () => api.revoke(user.email, grant.scope_path),
      `Revoked ${grant.scope_path} from ${user.name}. Its memories stay in Agent Memory.`,
    )
    if (ok) closeDialog()
  }

  // The dialog stays open after this, showing the new scope in its column.
  const createScope = async (path: string) => {
    if (known?.has(path)) {
      setError(`${path} is already registered.`)
      return false
    }
    return run(() => api.registerScope(path), `Registered ${path}.`)
  }

  // While a dialog is open its own errors show inside it, not behind the backdrop.
  const dialogError = error && (
    <p className="error" role="alert">
      {error}
    </p>
  )

  return (
    <section className="admin-access" aria-label="Access">
      <div className="admin-head">
        <div>
          <p>
            Who may read or write which Agent Memory scope. Everyone reads through these
            grants, so a change applies on their next Capture or Ask.
          </p>
        </div>
        <div className="admin-head-actions">
          <button
            type="button"
            className="btn-secondary"
            onClick={() => open({ kind: 'grant', user: null })}
          >
            <span aria-hidden="true">+</span> Add person or grant access
          </button>
          <button type="button" className="btn" onClick={() => open({ kind: 'scope' })}>
            <span aria-hidden="true">+</span> New scope
          </button>
        </div>
      </div>

      {registry.status === 'error' && (
        <p className="note admin-callout">
          Could not load the scopes in Agent Memory ({registry.message}). New scopes are
          still created when you grant them.
        </p>
      )}
      {known && (
        <datalist id={SCOPE_OPTIONS}>
          {[...known].sort().map((path) => (
            <option key={path} value={path} aria-label={path} />
          ))}
        </datalist>
      )}
      <datalist id={USER_OPTIONS}>
        {list.map((user) => (
          <option key={user.email} value={user.email} aria-label={user.name} />
        ))}
      </datalist>

      {error && !dialog && (
        <p className="error admin-callout" role="alert">
          {error}
        </p>
      )}
      {done && <output className="success admin-callout">{done}</output>}

      <section className="panel admin-users" aria-label="Users">
        {users.status === 'loading' && <p className="admin-muted">Loading users…</p>}
        {users.status === 'error' && (
          <p className="error" role="alert">
            Could not load users: {users.message}
          </p>
        )}
        {users.status === 'ready' && (
          <table className="admin-table">
            <thead>
              <tr>
                <th scope="col" className="admin-col-person">
                  Person
                </th>
                <th scope="col">Scope</th>
                <th scope="col" className="admin-col-fit">
                  Layer
                </th>
                <th scope="col" className="admin-col-fit">
                  Access
                </th>
                <th scope="col" className="admin-col-fit">
                  Revoke
                </th>
              </tr>
            </thead>
            {/* One tbody per person: their scopes are rows, and their name spans them. */}
            {list.map((user) => {
              const groupId = `admin-scopes-${user.email.replace(/[^a-z0-9]/gi, '-')}`
              const extra = user.grants.length - VISIBLE_SCOPES
              const collapsible = extra > 0
              const isOpen = expanded.has(user.email)
              const shown =
                collapsible && !isOpen
                  ? user.grants.slice(0, VISIBLE_SCOPES)
                  : user.grants
              // A warning on a hidden scope must not vanish with it.
              const hiddenMissing = known
                ? user.grants
                    .slice(VISIBLE_SCOPES)
                    .filter((g) => !known.has(g.scope_path)).length
                : 0
              const toggle = () => toggleExpanded(user.email)
              const span = Math.max(shown.length, 1) + (collapsible ? 1 : 0)
              const person = (
                <td rowSpan={span} data-label="Person" className="admin-person">
                  <span className="admin-person-head">
                    <span className="admin-name">{user.name}</span>
                    {collapsible && (
                      <button
                        type="button"
                        className="admin-toggle"
                        aria-expanded={isOpen}
                        aria-controls={groupId}
                        aria-label={
                          isOpen
                            ? `Show fewer scopes for ${user.name}`
                            : `Show all ${user.grants.length} scopes for ${user.name}`
                        }
                        onClick={toggle}
                      >
                        <svg
                          viewBox="0 0 16 16"
                          width="16"
                          height="16"
                          aria-hidden="true"
                        >
                          <path
                            d="M4 6l4 4 4-4"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="1.8"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      </button>
                    )}
                  </span>
                  <span className="admin-person-tags">
                    {user.is_admin && (
                      <span className="tag" data-tone="good">
                        admin
                      </span>
                    )}
                    {user.email === me.email && <span className="tag">you</span>}
                    <button
                      type="button"
                      className="admin-add-scope"
                      disabled={busy}
                      onClick={() => open({ kind: 'grant', user })}
                      aria-label={`Add a scope for ${user.name}`}
                    >
                      <span aria-hidden="true">+</span> Add scope
                    </button>
                  </span>
                  <span className="mono admin-muted admin-email">{user.email}</span>
                </td>
              )
              if (user.grants.length === 0) {
                return (
                  <tbody key={user.email} className="admin-person-group">
                    <tr>
                      {person}
                      <td colSpan={4} className="admin-muted">
                        No scopes
                      </td>
                    </tr>
                  </tbody>
                )
              }
              return (
                <tbody key={user.email} id={groupId} className="admin-person-group">
                  {shown.map((grant, index) => {
                    return (
                      <tr key={grant.scope_path}>
                        {index === 0 && person}
                        <td data-label="Scope" className="admin-scope">
                          <span className="mono admin-path">{grant.scope_path}</span>
                          {known && !known.has(grant.scope_path) && (
                            <span
                              className="tag"
                              data-tone="warn"
                              title="Writes here fail and reads come back empty until this scope exists"
                            >
                              not in Agent Memory
                            </span>
                          )}
                        </td>
                        <td data-label="Layer" className="admin-col-fit">
                          <span className="tag">{LAYER_LABELS[grant.layer]}</span>
                        </td>
                        <td data-label="Access" className="admin-col-fit">
                          <span
                            className="tag"
                            data-tone={grant.access === 'write' ? 'good' : undefined}
                          >
                            {grant.access === 'write' ? 'read & write' : 'read'}
                          </span>
                        </td>
                        <td className="admin-col-fit admin-grant-actions">
                          <button
                            type="button"
                            className="btn-secondary"
                            disabled={busy}
                            onClick={() => open({ kind: 'revoke', user, grant })}
                            aria-label={`Revoke ${grant.scope_path} from ${user.name}…`}
                          >
                            Revoke
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                  {collapsible && (
                    <tr className="admin-more-row">
                      <td colSpan={4}>
                        <button
                          type="button"
                          className="admin-more"
                          aria-expanded={isOpen}
                          aria-controls={groupId}
                          onClick={toggle}
                        >
                          {isOpen
                            ? 'Show fewer'
                            : `Show ${extra} more scope${extra === 1 ? '' : 's'}`}
                        </button>
                        {!isOpen && hiddenMissing > 0 && (
                          <span className="tag" data-tone="warn">
                            {hiddenMissing} not in Agent Memory
                          </span>
                        )}
                      </td>
                    </tr>
                  )}
                </tbody>
              )
            })}
          </table>
        )}
      </section>

      {dialog?.kind === 'grant' && (
        <Modal
          title={
            dialog.user
              ? `Add a scope for ${dialog.user.name}`
              : 'Add person or grant access'
          }
          description={
            dialog.user ? (
              <span className="mono">{dialog.user.email}</span>
            ) : (
              "Enter anyone's email, whether or not they're in the list. Someone who hasn't signed in yet is added now. When they first sign in, they also get their own personal scope and read access to the org."
            )
          }
          onClose={closeDialog}
        >
          <form className="admin-form" onSubmit={submitGrant} aria-label="Grant a scope">
            <div className="admin-fields">
              {!dialog.user && (
                <label className="admin-wide">
                  <span>Email</span>
                  <input
                    type="email"
                    list={USER_OPTIONS}
                    value={form.email}
                    required
                    placeholder="name@spreetail.com"
                    onChange={(e) => editForm({ ...form, email: e.target.value })}
                  />
                </label>
              )}
              {!dialog.user && grantee && (
                <p className="admin-wide admin-muted admin-note">
                  {grantee.name} is already in the list, so this adds a scope to them.
                </p>
              )}
              {!dialog.user && !grantee && form.email.trim() !== '' && (
                <label className="admin-wide">
                  <span>
                    Name <span className="admin-muted">(not signed in yet)</span>
                  </span>
                  <input
                    value={form.name}
                    maxLength={120}
                    placeholder="Vidyul Narayanan"
                    onChange={(e) => editForm({ ...form, name: e.target.value })}
                  />
                </label>
              )}
              <label className="admin-wide">
                <span>Scope</span>
                <input
                  className="mono"
                  list={SCOPE_OPTIONS}
                  value={form.scope_path}
                  required
                  placeholder={root ? `${root}/team/ops` : 'org/spreetail/team/ops'}
                  onChange={(e) => editForm({ ...form, scope_path: e.target.value })}
                />
              </label>
              {alreadyHeld && (
                <p className="admin-wide admin-muted admin-note">
                  {grantee?.name} already holds this scope (
                  {alreadyHeld.access === 'write' ? 'read & write' : 'read'}). Granting
                  replaces its access and layer.
                </p>
              )}
              <label>
                <span>Access</span>
                <select
                  value={form.access}
                  onChange={(e) =>
                    editForm({ ...form, access: e.target.value as Access })
                  }
                >
                  <option value="read">Read</option>
                  <option value="write">Read &amp; write</option>
                </select>
              </label>
              <label>
                <span>Layer</span>
                <select
                  value={form.layer}
                  onChange={(e) =>
                    editForm({ ...form, layer: e.target.value as GrantLayer })
                  }
                >
                  <option value="org">Org</option>
                  <option value="team">Team</option>
                  <option value="personal">Personal</option>
                </select>
              </label>
              {/* Sign-in creates a personal scope only when none is held, so this replaces it. */}
              {!grantee && form.layer === 'personal' && (
                <p className="admin-wide admin-note admin-warn-note">
                  Someone who hasn&apos;t signed in yet treats this as their personal
                  scope, so they won&apos;t get their own when they sign in.
                </p>
              )}
            </div>
            {missing && (
              <section
                className="admin-confirm"
                aria-label="Create scopes in Agent Memory"
              >
                <p>
                  {missing.length === 1 ? 'This scope does' : 'These scopes do'} not exist
                  in Agent Memory yet:
                </p>
                <ul className="mono">
                  {missing.map((path) => (
                    <li key={path}>{path}</li>
                  ))}
                </ul>
                <p className="admin-confirm-hint">
                  Granting creates {missing.length === 1 ? 'it' : 'them'} in the shared
                  Agent Memory context. Check the spelling, or pick an existing scope
                  instead.
                </p>
                <div className="admin-actions">
                  <button
                    type="button"
                    className="btn"
                    disabled={busy}
                    onClick={() => void sendGrant()}
                  >
                    Create {missing.length === 1 ? 'scope' : `${missing.length} scopes`}{' '}
                    and grant
                  </button>
                  <button
                    type="button"
                    className="btn-secondary"
                    disabled={busy}
                    onClick={() => setMissing(null)}
                  >
                    Go back
                  </button>
                </div>
              </section>
            )}
            {dialogError}
            <div className="admin-dialog-actions">
              <button type="button" className="btn-secondary" onClick={closeDialog}>
                Cancel
              </button>
              <button type="submit" className="btn" disabled={busy || missing !== null}>
                Grant
              </button>
            </div>
          </form>
        </Modal>
      )}

      {dialog?.kind === 'revoke' && (
        <Modal
          title="Revoke scope access?"
          description={
            <>
              {dialog.user.name} will no longer be able to{' '}
              {dialog.grant.access === 'write' ? 'read or write' : 'read'}{' '}
              <span className="mono">{dialog.grant.scope_path}</span>. The scope and its
              memories stay in Agent Memory, and you can grant it again later.
            </>
          }
          onClose={closeDialog}
        >
          <div className="admin-form">
            {dialogError}
            <div className="admin-dialog-actions">
              <button
                type="button"
                className="btn-secondary"
                disabled={busy}
                onClick={closeDialog}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn admin-danger"
                disabled={busy}
                onClick={() => void revoke(dialog.user, dialog.grant)}
                aria-label={`Revoke ${dialog.grant.scope_path} from ${dialog.user.name}`}
              >
                Revoke access
              </button>
            </div>
          </div>
        </Modal>
      )}

      {dialog?.kind === 'scope' && (
        <Modal
          title="New scope"
          description="Use + to add a team or a person, or pick any scope to add a sub-scope inside it. You only type the name: the path in front is fixed."
          onClose={closeDialog}
          wide
        >
          <NewScope
            root={root}
            known={known}
            loadError={registry.status === 'error' ? registry.message : null}
            busy={busy}
            onCreate={createScope}
            onGrant={(path, layer) =>
              open({
                kind: 'grant',
                user: null,
                prefill: {
                  scope_path: path,
                  layer,
                  // A personal scope is its owner's to write, as at sign-in.
                  access: layer === 'personal' ? 'write' : 'read',
                },
              })
            }
            onEdit={() => setError(null)}
            onClose={closeDialog}
            error={dialogError}
          />
        </Modal>
      )}
    </section>
  )
}

const SECTIONS = ['access', 'lab'] as const
type Section = (typeof SECTIONS)[number]
const SECTION_LABELS: Record<Section, string> = { access: 'Access', lab: 'Lab' }

/**
 * Admin has two sections, each with its own URL: #/admin/access (who may read
 * or write which scope) and #/admin/lab (memory jobs: consolidate, elaborate,
 * reflect). Both stay mounted once opened, so a running job keeps going.
 */
export default function AdminPage({ me, api = adminApi, labApi }: Props) {
  const section = useHashSubRoute(SECTIONS, 'access')
  const visited = useVisited(section)
  return (
    <main className="page admin-page">
      <div className="page-head">
        <h1>Admin</h1>
        <nav className="ask-modes admin-tabs" aria-label="Admin section">
          {SECTIONS.map((s) => (
            <a
              key={s}
              href={`#/admin/${s}`}
              aria-current={s === section ? 'page' : undefined}
            >
              {SECTION_LABELS[s]}
            </a>
          ))}
        </nav>
      </div>
      {visited.map((s) => (
        <KeepAlive key={s} active={s === section}>
          {s === 'lab' ? <MemoryLab api={labApi} /> : <AdminAccess me={me} api={api} />}
        </KeepAlive>
      ))}
    </main>
  )
}
