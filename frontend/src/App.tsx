import { useEffect, useState } from 'react'
import { getMe, logout, type Me } from '@/api/auth'
import { ApiError } from '@/api/client'
import { USE_MOCK_API } from '@/api/config'
import Account from '@/components/Account'
import { HeaderSlotContext } from '@/components/headerSlotContext'
import Login from '@/components/Login'
import { useHashRoute } from '@/hooks/useHashRoute'
import { useTheme } from '@/hooks/useTheme'
import AdminPage from '@/pages/AdminPage'
import AskPage from '@/pages/AskPage'
import BrainPage from '@/pages/BrainPage'
import CapturePage from '@/pages/CapturePage'

const PAGES = [
  { route: 'capture', label: 'Capture' },
  { route: 'ask', label: 'Ask' },
  { route: 'admin', label: 'Admin' },
  { route: 'brain', label: 'Brain' },
] as const

type Route = (typeof PAGES)[number]['route']

// Stable lists, since the router watches them. Admin is only for admins.
const ADMIN_ROUTES: readonly Route[] = PAGES.map((page) => page.route)
const USER_ROUTES: readonly Route[] = ADMIN_ROUTES.filter((route) => route !== 'admin')

type Session =
  { status: 'checking' } | { status: 'signed-out' } | { status: 'signed-in'; me: Me }

/** Shows the login until /auth/me succeeds; a 401 is the normal signed-out answer. */
export default function App() {
  const [session, setSession] = useState<Session>({ status: 'checking' })

  useEffect(() => {
    const controller = new AbortController()
    getMe(controller.signal)
      .then((me) => setSession({ status: 'signed-in', me }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        if (!(error instanceof ApiError && error.status === 401)) console.warn(error)
        setSession({ status: 'signed-out' })
      })
    return () => controller.abort()
  }, [])

  if (session.status === 'checking') {
    return (
      <main className="app-loading">
        <p>Loading…</p>
      </main>
    )
  }

  if (session.status === 'signed-out') {
    return <Login onSignedIn={(me) => setSession({ status: 'signed-in', me })} />
  }

  const signOut = async () => {
    await logout().catch(() => undefined)
    setSession({ status: 'signed-out' })
  }

  return (
    <Shell
      me={session.me}
      onMe={(me) => setSession({ status: 'signed-in', me })}
      onSignedOut={() => setSession({ status: 'signed-out' })}
      onSignOut={() => void signOut()}
    />
  )
}

interface ShellProps {
  me: Me
  /** A fresher copy of the signed-in user, e.g. after an admin changed their grants. */
  onMe: (me: Me) => void
  /** The session ended elsewhere (401). */
  onSignedOut: () => void
  onSignOut: () => void
}

function Shell({ me, onMe, onSignedOut, onSignOut }: ShellProps) {
  const routes = me.is_admin ? ADMIN_ROUTES : USER_ROUTES
  const route = useHashRoute<Route>(routes, 'capture')

  // Grants can change while signed in (on Admin, or by another admin), so
  // re-read them on every page change rather than trusting the sign-in copy.
  useEffect(() => {
    const controller = new AbortController()
    getMe(controller.signal)
      .then(onMe)
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        if (error instanceof ApiError && error.status === 401) onSignedOut()
      })
    return () => controller.abort()
    // Only the page change should trigger this, not new callback identities.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [route])
  const [theme, toggleTheme] = useTheme()
  const [slot, setSlot] = useState<HTMLDivElement | null>(null)

  return (
    <HeaderSlotContext.Provider value={slot}>
      <div className="shell">
        <header className="topbar">
          <div className="topbar-inner">
            <span className="brand">
              MemBrain <span className="mono">POC</span>
            </span>
            <nav aria-label="Main" className="topnav">
              {PAGES.filter((page) => routes.includes(page.route)).map((page) => (
                <a
                  key={page.route}
                  href={`#/${page.route}`}
                  aria-current={page.route === route ? 'page' : undefined}
                >
                  {page.label}
                </a>
              ))}
            </nav>
            <div className="topbar-end">
              <div className="topbar-who" ref={setSlot} />
              {USE_MOCK_API && (
                <span
                  className="tag"
                  data-tone="note"
                  title="Unset VITE_USE_MOCK_API to call the real backend"
                >
                  mock API
                </span>
              )}
              <Account
                me={me}
                dark={theme === 'dark'}
                onToggleTheme={toggleTheme}
                onSignOut={onSignOut}
              />
            </div>
          </div>
        </header>
        {/* Keyed by user, so signing in as someone else starts each page afresh. */}
        {route === 'capture' && <CapturePage key={me.email} me={me} />}
        {route === 'ask' && <AskPage key={me.email} me={me} />}
        {route === 'admin' && <AdminPage key={me.email} me={me} />}
        {route === 'brain' && <BrainPage key={me.email} me={me} />}
      </div>
    </HeaderSlotContext.Provider>
  )
}
