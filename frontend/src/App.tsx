import { useEffect, useRef, useState } from 'react'
import { getMe, logout, type Me } from '@/api/auth'
import { clearLabResults } from '@/components/admin/labResults'
import { clearChats } from '@/components/ask/chatStore'
import { clearReflections } from '@/components/ask/reflectStore'
import { ApiError } from '@/api/client'
import { USE_MOCK_API } from '@/api/config'
import Account from '@/components/Account'
import { HeaderSlotContext } from '@/components/headerSlotContext'
import KeepAlive from '@/components/KeepAlive'
import Login from '@/components/Login'
import { useHashRoute, useLastHashes } from '@/hooks/useHashRoute'
import { useTheme } from '@/hooks/useTheme'
import { useVisited } from '@/hooks/useVisited'
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

  // Chats and memory job results are kept until sign-out, so the next person on this browser starts clean.
  const signedOut = () => {
    clearChats()
    clearReflections()
    clearLabResults()
    setSession({ status: 'signed-out' })
  }

  const signOut = async () => {
    await logout().catch(() => undefined)
    signedOut()
  }

  return (
    <Shell
      // Keyed by user, so signing in as someone else starts every page afresh.
      key={session.me.email}
      me={session.me}
      onMe={(me) => setSession({ status: 'signed-in', me })}
      onSignedOut={signedOut}
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
  const visited = useVisited(route)
  // Each nav link goes back to where that page was left, e.g. #/ask/chat.
  const lastHashes = useLastHashes()

  // Grants can change while signed in (on Admin, or by another admin), so
  // re-read them on every page change rather than trusting the sign-in copy.
  // Not on the first page: App fetched /auth/me a moment ago to sign in. The
  // ref (not a flag) also keeps StrictMode's effect re-run from fetching.
  const readFor = useRef(route)
  useEffect(() => {
    if (readFor.current === route) return
    readFor.current = route
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
                  href={lastHashes[page.route] ?? `#/${page.route}`}
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
        {/* A page stays mounted once opened, so switching tabs keeps its work. */}
        {/* routes too: someone who stops being an admin loses the kept Admin page. */}
        {PAGES.filter(
          (page) => visited.includes(page.route) && routes.includes(page.route),
        ).map(({ route: name }) => (
          <KeepAlive key={name} active={name === route}>
            {name === 'capture' && <CapturePage me={me} />}
            {name === 'ask' && <AskPage me={me} />}
            {name === 'admin' && <AdminPage me={me} />}
            {name === 'brain' && <BrainPage me={me} />}
          </KeepAlive>
        ))}
      </div>
    </HeaderSlotContext.Provider>
  )
}
