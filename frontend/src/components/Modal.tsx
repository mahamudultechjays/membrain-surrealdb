import { useContext, useEffect, useId, useRef, type ReactNode } from 'react'
import { PageActiveContext } from '@/components/pageActiveContext'

interface Props {
  title: string
  /** A line under the title, e.g. whose scopes are being changed. */
  description?: ReactNode
  onClose: () => void
  children: ReactNode
}

const FOCUSABLE =
  'input:not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), [href]'

/**
 * A centred dialog over a dimmed page. Escape or a click on the backdrop
 * closes it, Tab stays inside it, and focus goes back to whatever opened it.
 */
export default function Modal({ title, description, onClose, children }: Props) {
  const titleId = useId()
  const descriptionId = useId()
  const panel = useRef<HTMLDialogElement>(null)
  // Read through a ref so a new onClose each render doesn't re-run the focus effect.
  const close = useRef(onClose)
  useEffect(() => {
    close.current = onClose
  }, [onClose])

  // A dialog left open on a page the user switched away from waits, hidden,
  // without holding the scroll lock or the keyboard.
  const active = useContext(PageActiveContext)

  useEffect(() => {
    if (!active) return
    const opener =
      document.activeElement instanceof HTMLElement ? document.activeElement : null
    // The first field, not the close button in the corner.
    const body = panel.current?.querySelector('.modal-body')
    ;(
      body?.querySelector<HTMLElement>(FOCUSABLE) ??
      panel.current?.querySelector<HTMLElement>(FOCUSABLE)
    )?.focus()
    const { overflow } = document.body.style
    document.body.style.overflow = 'hidden'

    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        close.current()
        return
      }
      if (event.key !== 'Tab' || !panel.current) return
      const items = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)]
      const first = items[0]
      const last = items[items.length - 1]
      if (!first || !last) return
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = overflow
      opener?.focus()
    }
  }, [active])

  return (
    <div
      className="modal-backdrop"
      // Pointer-only convenience: keyboard users close with Escape or the × button.
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close.current()
      }}
    >
      {/* Rendered open, not via showModal(): the backdrop, focus trap and Escape
          above make it modal, and it works the same in tests (jsdom). */}
      <dialog
        ref={panel}
        open
        className="modal panel"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
      >
        <div className="modal-head">
          <div>
            <h2 id={titleId}>{title}</h2>
            {description && (
              <p id={descriptionId} className="modal-description">
                {description}
              </p>
            )}
          </div>
          <button
            type="button"
            className="modal-close"
            onClick={() => close.current()}
            aria-label="Close"
          >
            <span aria-hidden="true">×</span>
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </dialog>
    </div>
  )
}
