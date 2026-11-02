import type { Me } from '@/api/auth'

interface AccountProps {
  me: Me
  onSignOut: () => void
}

/** The signed-in user and the memory scopes our backend lets them read or write. */
export default function Account({ me, onSignOut }: AccountProps) {
  return (
    <section aria-labelledby="account-heading">
      <div className="account-head">
        <div>
          <h2 id="account-heading">
            {me.name} {me.is_admin && <span className="badge">admin</span>}
          </h2>
          <p className="muted">{me.email}</p>
        </div>
        <button type="button" onClick={onSignOut}>
          Sign out
        </button>
      </div>
      <h3>Your memory scopes</h3>
      <ul className="status">
        {me.grants.map((grant) => (
          <li key={grant.scope_path}>
            <span>
              <code>{grant.scope_path}</code>{' '}
              <span className="muted">({grant.layer})</span>
            </span>
            <span>{grant.access === 'write' ? 'read & write' : 'read'}</span>
          </li>
        ))}
      </ul>
    </section>
  )
}
