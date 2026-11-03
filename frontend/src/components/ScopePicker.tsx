import { useEffect, useId, useRef, useState } from 'react'
export interface PickerOption {
  id: string
  name: string
  /** A second, quieter line of detail, e.g. a scope path. */
  detail?: string
}

interface Props {
  options: readonly PickerOption[]
  /** Selected ids, in the order they were picked. */
  value: string[]
  onChange: (ids: string[]) => void
  /** Capture writes to one scope; an admin can ask as several people at once. */
  multiple?: boolean
  label: string
  /** Shown on the button when every option is picked, e.g. "All spaces". */
  allLabel?: string
}

/** A header dropdown, like the mockup's "View as" control. */
export default function ScopePicker({
  options,
  value,
  onChange,
  multiple = false,
  label,
  allLabel,
}: Props) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const menuId = useId()

  // Close on a click outside or Escape, as a native select would.
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

  const toggle = (id: string) => {
    if (!multiple) {
      onChange([id])
      setOpen(false)
      trigger.current?.focus()
      return
    }
    if (!value.includes(id)) return onChange([...value, id])
    // Keep at least one selected.
    if (value.length > 1) onChange(value.filter((s) => s !== id))
  }

  const names = value
    .map((id) => options.find((o) => o.id === id)?.name)
    .filter((name): name is string => Boolean(name))
  const summary =
    allLabel && options.length > 1 && value.length === options.length
      ? allLabel
      : names.join(' + ')

  return (
    <div className="scope-dropdown" ref={root}>
      <span className="scope-dropdown-label" aria-hidden="true">
        {label}
      </span>
      <button
        ref={trigger}
        type="button"
        className="scope-trigger"
        aria-label={`${label}: ${summary || 'nothing'}`}
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((o) => !o)}
      >
        <span>{summary || 'Choose…'}</span>
        <span aria-hidden="true" className="scope-caret">
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.25"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="m6 9 6 6 6-6" />
          </svg>
        </span>
      </button>
      {open && (
        <fieldset id={menuId} className="scope-menu">
          <legend className="visually-hidden">{label}</legend>
          {options.map((option) => {
            const checked = value.includes(option.id)
            return (
              <label key={option.id} className="scope-option" data-checked={checked}>
                <input
                  type={multiple ? 'checkbox' : 'radio'}
                  name={multiple ? undefined : menuId}
                  checked={checked}
                  onChange={() => toggle(option.id)}
                />
                <span className="scope-name">{option.name}</span>
                {option.detail && (
                  <span className="mono scope-meta">{option.detail}</span>
                )}
              </label>
            )
          })}
        </fieldset>
      )}
    </div>
  )
}
