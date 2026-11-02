import { useEffect, useState } from 'react'
import { getMe, logout, type Me } from '@/api/auth'
import { ApiError } from '@/api/client'
import Account from '@/components/Account'
import HealthStatus from '@/components/HealthStatus'
import Login from '@/components/Login'

type Session =
  { status: 'checking' } | { status: 'signed-out' } | { status: 'signed-in'; me: Me }

export default function App() {
  const [session, setSession] = useState<Session>({ status: 'checking' })

  useEffect(() => {
    const controller = new AbortController()
    getMe(controller.signal)
      .then((me) => setSession({ status: 'signed-in', me }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        // 401 is the normal signed-out answer; anything else still shows the login.
        if (!(error instanceof ApiError && error.status === 401)) console.warn(error)
        setSession({ status: 'signed-out' })
      })
    return () => controller.abort()
  }, [])

  if (session.status === 'checking') return <main className="app">Loading…</main>

  if (session.status === 'signed-out') {
    return <Login onSignedIn={(me) => setSession({ status: 'signed-in', me })} />
  }

  const signOut = async () => {
    await logout().catch(() => undefined)
    setSession({ status: 'signed-out' })
  }

  return (
    <main className="app">
      <h1>Membrain SurrealDB POC</h1>
      <Account me={session.me} onSignOut={signOut} />
      <HealthStatus />
    </main>
  )
}
