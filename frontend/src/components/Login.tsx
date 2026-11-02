import { useState, type FormEvent } from 'react'
import { devLogin, getAuthConfig, SSO_LOGIN_URL, type Me } from '@/api/auth'
import { useAsync } from '@/hooks/useAsync'

interface LoginProps {
  onSignedIn: (me: Me) => void
}

/** Same flow as membrain: one SSO button that hands off to Microsoft Entra ID.
 *  When SSO is not configured locally, an email login stands in for the demo. */
export default function Login({ onSignedIn }: LoginProps) {
  const config = useAsync(getAuthConfig)
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onSignedIn(await devLogin(email.trim(), name.trim()))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="login">
      <div className="login-card">
        <div className="wordmark">
          Mem<span>Brain</span>
        </div>
        <h1>Welcome back</h1>
        <p className="muted">Sign in with your Spreetail account.</p>

        {config.status === 'loading' && (
          <p className="muted">Checking sign-in options…</p>
        )}
        {config.status === 'error' && <p role="alert">The API is unreachable.</p>}

        {config.status === 'success' && config.data.sso_enabled && (
          <>
            <button
              type="button"
              className="primary"
              onClick={() => window.location.assign(SSO_LOGIN_URL)}
            >
              Login with SSO
            </button>
            <p className="muted small">
              You&apos;ll be redirected to Microsoft Entra ID.
            </p>
          </>
        )}

        {config.status === 'success' && config.data.dev_login_enabled && (
          <form onSubmit={submit} aria-label="Developer sign-in">
            <p className="muted small">Development sign-in (SSO not configured)</p>
            <label>
              Email
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
              />
            </label>
            <label>
              Full name
              <input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoComplete="name"
              />
            </label>
            <button type="submit" className="primary" disabled={busy}>
              {busy ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        )}

        {error && <p role="alert">{error}</p>}
      </div>
    </main>
  )
}
