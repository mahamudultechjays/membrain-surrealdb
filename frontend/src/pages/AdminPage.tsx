import { useEffect, useState, type FormEvent } from 'react'
import { adminApi, type AdminApi, type GrantInput, type UserGrants } from '@/api/admin'
import type { Access, Grant, GrantLayer, Me } from '@/api/auth'
import type { LabApi } from '@/api/lab'
import { cleanPath, unregisteredScopes } from '@/api/scopePaths'
import MemoryLab from '@/components/admin/MemoryLab'
import { LAYER_LABELS } from '@/components/ask/layers'
import { isAbort, messageOf } from '@/components/capture/format'
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

/**
 * Who may read or write which Agent Memory scope. The backend reaches Agent
 * Memory with one admin key, so these grants are the only thing keeping
 * people's memories apart.
 */
export default function AdminPage({ me, api = adminApi, labApi }: Props) {
  const [users, setUsers] = useState<UsersState>({ status: 'loading' })
  const [registry, setRegistry] = useState<RegistryState>({ status: 'loading' })
  const [form, setForm] = useState<GrantForm>(EMPTY_GRANT)
  // Scopes the grant would create; set until the admin confirms or goes back.
  const [missing, setMissing] = useState<string[] | null>(null)
  const [newScope, setNewScope] = useState('')
  const [revoking, setRevoking] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)

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
  const existingUser = list.find((u) => u.email === form.email.trim().toLowerCase())

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

  const editForm = (next: GrantForm) => {
    setForm(next)
    setMissing(null)
  }

  const sendGrant = async () => {
    const email = form.email.trim().toLowerCase()
    const grant: GrantInput = {
      scope_path: cleanPath(form.scope_path),
      access: form.access,
      layer: form.layer,
      name: existingUser ? null : form.name.trim() || null,
    }
    const ok = await run(
      () => api.grant(email, grant),
      `Granted ${grant.access === 'write' ? 'read and write' : 'read'} on ${grant.scope_path} to ${existingUser?.name ?? email}.`,
    )
    if (ok) {
      setForm(EMPTY_GRANT)
      setMissing(null)
    }
  }

  // A grant registers any new path, so a typo would quietly create a scope: ask first.
  const submitGrant = (event: FormEvent) => {
    event.preventDefault()
    const path = cleanPath(form.scope_path)
    const unknown = known && root ? unregisteredScopes([path], known, root) : []
    if (unknown.length) {
      setError(null)
      setDone(null)
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
    if (ok) setRevoking(null)
  }

  const register = async (event: FormEvent) => {
    event.preventDefault()
    const path = cleanPath(newScope)
    if (known?.has(path)) {
      setDone(null)
      setError(`${path} is already registered.`)
      return
    }
    if (await run(() => api.registerScope(path), `Registered ${path}.`)) setNewScope('')
  }

  return (
    <main className="page admin-page">
      <div className="page-head">
        <h1>Admin</h1>
        <p>
          Who may read or write which Agent Memory scope. Everyone reads through these
          grants, so a change applies on their next Capture or Ask.
        </p>
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

      {error && (
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
                <th scope="col">Name</th>
                <th scope="col">Scopes</th>
              </tr>
            </thead>
            <tbody>
              {list.map((user) => (
                <tr key={user.email}>
                  <td data-label="Name" className="admin-person">
                    <span className="admin-name">{user.name}</span>
                    {user.is_admin && (
                      <span className="tag" data-tone="good">
                        admin
                      </span>
                    )}
                    {user.email === me.email && <span className="tag">you</span>}
                    <span className="mono admin-muted admin-email">{user.email}</span>
                  </td>
                  <td data-label="Scopes">
                    {user.grants.length === 0 ? (
                      <span className="admin-muted">No scopes</span>
                    ) : (
                      <ul className="admin-grants">
                        {user.grants.map((grant) => {
                          const key = `${user.email} ${grant.scope_path}`
                          return (
                            <li key={grant.scope_path} className="admin-grant">
                              <span className="mono admin-path">{grant.scope_path}</span>
                              <span className="admin-grant-tags">
                                <span className="tag">{LAYER_LABELS[grant.layer]}</span>
                                <span
                                  className="tag"
                                  data-tone={
                                    grant.access === 'write' ? 'good' : undefined
                                  }
                                >
                                  {grant.access === 'write' ? 'read & write' : 'read'}
                                </span>
                                {known && !known.has(grant.scope_path) && (
                                  <span
                                    className="tag"
                                    data-tone="warn"
                                    title="Writes here fail and reads come back empty until this scope exists"
                                  >
                                    not in Agent Memory
                                  </span>
                                )}
                              </span>
                              <span className="admin-grant-actions">
                                {revoking === key ? (
                                  <>
                                    <button
                                      type="button"
                                      className="btn admin-danger"
                                      disabled={busy}
                                      onClick={() => void revoke(user, grant)}
                                      aria-label={`Revoke ${grant.scope_path} from ${user.name}`}
                                    >
                                      Revoke
                                    </button>
                                    <button
                                      type="button"
                                      className="btn-secondary"
                                      disabled={busy}
                                      onClick={() => setRevoking(null)}
                                    >
                                      Keep
                                    </button>
                                  </>
                                ) : (
                                  <button
                                    type="button"
                                    className="btn-secondary"
                                    disabled={busy}
                                    onClick={() => setRevoking(key)}
                                    aria-label={`Revoke ${grant.scope_path} from ${user.name}…`}
                                  >
                                    Revoke
                                  </button>
                                )}
                              </span>
                            </li>
                          )
                        })}
                      </ul>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <div className="admin-forms">
        <form
          className="panel admin-form"
          onSubmit={submitGrant}
          aria-label="Grant a scope"
        >
          <h2>Grant a scope</h2>
          <div className="admin-fields">
            <label>
              <span>Person</span>
              <input
                type="email"
                list={USER_OPTIONS}
                value={form.email}
                required
                placeholder="name@spreetail.com"
                onChange={(e) => editForm({ ...form, email: e.target.value })}
              />
            </label>
            {!existingUser && form.email.trim() !== '' && (
              <label>
                <span>
                  Name <span className="admin-muted">(not signed in yet)</span>
                </span>
                <input
                  value={form.name}
                  maxLength={120}
                  placeholder="Vidyul Kumar"
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
            <label>
              <span>Access</span>
              <select
                value={form.access}
                onChange={(e) => editForm({ ...form, access: e.target.value as Access })}
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
          </div>
          {missing && (
            <section className="admin-confirm" aria-label="Create scopes in Agent Memory">
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
                  Create {missing.length === 1 ? 'scope' : `${missing.length} scopes`} and
                  grant
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
          <button type="submit" className="btn" disabled={busy || missing !== null}>
            Grant
          </button>
        </form>

        <form
          className="panel admin-form"
          onSubmit={register}
          aria-label="Register a scope"
        >
          <h2>Register a scope</h2>
          <p className="admin-muted admin-form-hint">
            Creates an empty scope, for example a new team, before anyone is granted it.
          </p>
          <label className="admin-field">
            <span>Scope path</span>
            <input
              className="mono"
              value={newScope}
              required
              placeholder={root ? `${root}/team/eng` : 'org/spreetail/team/eng'}
              onChange={(e) => setNewScope(e.target.value)}
            />
          </label>
          <button type="submit" className="btn" disabled={busy}>
            Register scope
          </button>
        </form>
      </div>

      <MemoryLab api={labApi} />
    </main>
  )
}
