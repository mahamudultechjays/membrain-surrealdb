import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import type { Me } from '@/api/auth'

interface AccountProps {
  me: Me
  dark: boolean
  onToggleTheme: () => void
  onSignOut: () => void
}

/**
 * The signed-in user as an initial in a circle, top right. It opens a small
 * panel with who they are, the theme switch, and Sign out.
 */
export default function Account({ me, dark, onToggleTheme, onSignOut }: AccountProps) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const panelId = useId()
  const initial = (me.name.trim()[0] ?? me.email[0] ?? '?').toUpperCase()

  // Close on a click outside or Escape, like the header's other dropdown.
  useEffect(() => {
    if (!open) return
    const onPointer = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      setOpen(false)
      trigger.current?.focus()
    }
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div className="account" ref={root}>
      <button
        ref={trigger}
        type="button"
        className="account-avatar"
        aria-label={`Account: ${me.name}`}
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
      >
        <span aria-hidden="true">{initial}</span>
      </button>
      {open && (
        <div id={panelId} className="account-menu">
          <div className="account-who">
            <span className="account-avatar account-avatar-large" aria-hidden="true">
              {initial}
            </span>
            <span className="account-id">
              <span className="account-name">
                {me.name}
                {me.is_admin && (
                  <span className="tag" data-tone="good">
                    admin
                  </span>
                )}
              </span>
              <span className="account-email">{me.email}</span>
            </span>
          </div>
          <button
            type="button"
            className="account-item"
            role="switch"
            aria-checked={dark}
            onClick={onToggleTheme}
          >
            {dark ? <MoonIcon /> : <SunIcon />}
            <span>Dark theme</span>
            <span className="account-switch" aria-hidden="true" />
          </button>
          <button type="button" className="account-item" onClick={onSignOut}>
            <SignOutIcon />
            <span>Sign out</span>
          </button>
        </div>
      )}
    </div>
  )
}

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  )
}

function SunIcon() {
  return (
    <Icon>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </Icon>
  )
}

function MoonIcon() {
  return (
    <Icon>
      <path d="M20.5 14.2A8.5 8.5 0 1 1 9.8 3.5a6.6 6.6 0 0 0 10.7 10.7Z" />
    </Icon>
  )
}

function SignOutIcon() {
  return (
    <Icon>
      <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 17l-5-5 5-5M5 12h10" />
    </Icon>
  )
}
