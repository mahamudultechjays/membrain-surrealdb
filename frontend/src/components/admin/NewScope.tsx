import {
  Fragment,
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react'
import type { GrantLayer } from '@/api/auth'
import { childScopes, personSlug, teamSlug, type ChildScope } from '@/api/scopePaths'

/** Where a new scope can go. The org scope itself is fixed, so it has no "+". */
type AreaKey = 'team' | 'user'

interface Area {
  key: AreaKey
  title: string
  /** The path segment under the org scope: org/spreetail/<segment>/<name>. */
  segment: string
  /** The "+" button's name. */
  addLabel: string
  label: string
  placeholder: string
  hint: string
  slug: (text: string) => string
  /** What a grant of a top-level scope here usually is. */
  layer: GrantLayer
}

const AREAS: readonly Area[] = [
  {
    key: 'team',
    title: 'Team',
    segment: 'team',
    addLabel: 'Add a team scope',
    label: 'Team name',
    placeholder: 'e.g. Customer Support',
    hint: 'One space the whole team shares.',
    slug: teamSlug,
    layer: 'team',
  },
  {
    key: 'user',
    title: 'Individual',
    segment: 'user',
    addLabel: 'Add an individual scope',
    label: "Person's name",
    placeholder: 'e.g. Priya Nair',
    hint: 'Their own space, named the way sign-in names it.',
    slug: personSlug,
    layer: 'personal',
  },
]

/** Where the add field is open: at the top of a column, or inside a listed scope. */
interface Target {
  area: AreaKey
  /** The scope to add inside; null adds a new team or person. */
  parent: string | null
}

interface Props {
  /** The org scope, e.g. org/spreetail; undefined until the scopes load. */
  root: string | undefined
  known: ReadonlySet<string> | null
  loadError: string | null
  busy: boolean
  /** Registers the path; resolves true once it exists. */
  onCreate: (path: string) => Promise<boolean>
  /** Opens the grant dialog for a scope just created. */
  onGrant: (path: string, layer: GrantLayer) => void
  onEdit: () => void
  onClose: () => void
  /** The dialog's error line, if any. */
  error: ReactNode
}

/**
 * New scope, in three columns: Org, Team and Individual. "+" adds a team or a
 * person by name; any listed scope can be opened to add a sub-scope inside it.
 * The path in front is always fixed, so scopes land where the app expects them.
 */
export default function NewScope({
  root,
  known,
  loadError,
  busy,
  onCreate,
  onGrant,
  onEdit,
  onClose,
  error,
}: Props) {
  const ids = useId()
  const [target, setTarget] = useState<Target | null>(null)
  const [text, setText] = useState('')
  // Scopes whose sub-scopes are shown.
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set())
  const [created, setCreated] = useState<{ path: string; layer: GrantLayer } | null>(null)
  const nameInput = useRef<HTMLInputElement>(null)
  // Counts each time the field opens, so it takes focus every time.
  const [opened, setOpened] = useState(0)

  useEffect(() => {
    if (opened) nameInput.current?.focus()
  }, [opened])

  if (!root || !known) {
    return (
      <div className="admin-form">
        <p
          className={loadError ? 'error' : 'admin-muted'}
          role={loadError ? 'alert' : undefined}
        >
          {loadError
            ? `Could not load the scopes in Agent Memory (${loadError}), so new ones can't be placed yet.`
            : 'Loading scopes…'}
        </p>
        <div className="admin-dialog-actions">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    )
  }

  const rowId = (path: string) => `${ids}-row-${path}`
  const addId = (area: AreaKey) => `${ids}-add-${area}`

  const toggle = (path: string, show?: boolean) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      if (show ?? !next.has(path)) next.add(path)
      else next.delete(path)
      return next
    })

  const openField = (next: Target) => {
    setTarget(next)
    setText('')
    setOpened((n) => n + 1)
    // Show what is already inside, so a duplicate is easy to spot.
    if (next.parent) toggle(next.parent, true)
    onEdit()
  }

  /** Closes the field and puts focus back on what opened it. */
  const closeField = () => {
    if (!target) return
    setTarget(null)
    setText('')
    document
      .getElementById(target.parent ? rowId(target.parent) : addId(target.area))
      ?.focus()
  }

  const others = childScopes(root, known).filter(
    (child) => !AREAS.some((area) => area.segment === child.name),
  )

  /** The add field, at the top of a column or under the scope it adds inside. */
  const field = (area: Area, top: string) => {
    const parent = target?.parent ?? null
    const base = parent ?? top
    // A new person is named like sign-in names them; anything else is a plain slug.
    const slug = parent ? teamSlug(text) : area.slug(text)
    const path = `${base}/${slug}`
    const inside = parent?.slice(top.length + 1)
    const exists = slug !== '' && known.has(path)
    const problem =
      text.trim() === ''
        ? null
        : slug === ''
          ? 'Use letters or numbers.'
          : exists
            ? 'That scope already exists.'
            : null
    const inputId = `${ids}-name`
    const previewId = `${ids}-preview`

    const submit = async (event: FormEvent) => {
      event.preventDefault()
      if (!slug || exists) return
      if (await onCreate(path)) {
        // A sub-scope is shared work, not anyone's personal space.
        setCreated({ path, layer: parent ? 'team' : area.layer })
        if (parent) toggle(parent, true)
        closeField()
      }
    }

    return (
      <form
        className="scope-new"
        onSubmit={submit}
        aria-label={
          inside ? `New sub-scope in ${inside}` : `New ${area.title.toLowerCase()} scope`
        }
      >
        <label htmlFor={inputId} className="scope-new-label">
          {inside ? `Sub-scope in ${inside}` : area.label}
        </label>
        <div className="scope-new-field">
          {inside && (
            <span className="mono scope-new-prefix" aria-hidden="true">
              {inside}/
            </span>
          )}
          <input
            ref={nameInput}
            id={inputId}
            value={text}
            maxLength={60}
            autoComplete="off"
            spellCheck={false}
            placeholder={inside ? 'e.g. Returns' : area.placeholder}
            aria-describedby={previewId}
            aria-invalid={problem ? true : undefined}
            onChange={(e) => {
              setText(e.target.value)
              onEdit()
            }}
            onKeyDown={(e) => {
              // Escape closes this field, not the whole dialog.
              if (e.key !== 'Escape') return
              e.preventDefault()
              e.stopPropagation()
              closeField()
            }}
          />
        </div>
        <p
          id={previewId}
          className={problem ? 'scope-new-preview admin-warn-note' : 'scope-new-preview'}
        >
          {problem ?? (
            <>
              {inside
                ? 'A project or topic, kept apart from the rest. '
                : `${area.hint} `}
              Creates{' '}
              <span className="mono">{breakAtSlashes(slug ? path : `${base}/…`)}</span>
            </>
          )}
        </p>
        <div className="scope-new-actions">
          <button type="button" className="scope-text-btn" onClick={closeField}>
            Cancel
          </button>
          <button type="submit" className="btn" disabled={busy || !slug || exists}>
            {busy ? 'Creating…' : 'Create'}
          </button>
        </div>
      </form>
    )
  }

  return (
    <div className="admin-form">
      <div className="scope-cols">
        <section className="scope-col" aria-labelledby={`${ids}-org`}>
          <div className="scope-col-head">
            <div>
              <h3 id={`${ids}-org`}>Org</h3>
              <p className="mono scope-col-path">{root}</p>
            </div>
          </div>
          <p className="scope-col-note">The one org scope. Everyone reads it.</p>
          {others.length > 0 && (
            <>
              <h4 className="scope-sub">Other areas</h4>
              <ScopeTree
                items={others}
                known={known}
                expanded={expanded}
                onToggle={toggle}
                created={null}
                rowId={rowId}
              />
            </>
          )}
        </section>

        {AREAS.map((area) => {
          const top = `${root}/${area.segment}`
          const here = target?.area === area.key ? target : null
          const items = childScopes(top, known)
          return (
            <section
              key={area.key}
              className="scope-col"
              aria-labelledby={`${ids}-${area.key}`}
            >
              <div className="scope-col-head">
                <div>
                  <h3 id={`${ids}-${area.key}`}>{area.title}</h3>
                  <p className="mono scope-col-path">{top}/</p>
                </div>
                <button
                  type="button"
                  id={addId(area.key)}
                  className="scope-add"
                  aria-label={area.addLabel}
                  aria-expanded={here !== null && here.parent === null}
                  onClick={() =>
                    here && here.parent === null
                      ? closeField()
                      : openField({ area: area.key, parent: null })
                  }
                >
                  <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
                    <path
                      d="M8 3v10M3 8h10"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                    />
                  </svg>
                </button>
              </div>

              {here && here.parent === null && field(area, top)}

              {items.length ? (
                <ScopeTree
                  items={items}
                  known={known}
                  expanded={expanded}
                  onToggle={toggle}
                  created={created?.path ?? null}
                  rowId={rowId}
                  picked={here?.parent ?? null}
                  onPick={(item) =>
                    here?.parent === item.path
                      ? closeField()
                      : openField({ area: area.key, parent: item.path })
                  }
                  form={here?.parent ? field(area, top) : null}
                />
              ) : (
                <p className="scope-col-note">
                  No {area.title.toLowerCase()} scopes yet.
                </p>
              )}
            </section>
          )
        })}
      </div>

      {created && (
        <output className="success scope-created">
          Created <span className="mono">{created.path}</span>.{' '}
          <button
            type="button"
            className="admin-more"
            onClick={() => onGrant(created.path, created.layer)}
          >
            Grant access…
          </button>
        </output>
      )}
      {error}
      <div className="admin-dialog-actions">
        <button type="button" className="btn-secondary" onClick={onClose}>
          Done
        </button>
      </div>
    </div>
  )
}

/** A path that wraps only after a slash, never inside a name. */
function breakAtSlashes(path: string): ReactNode {
  return path.split('/').map((part, i) => (
    <Fragment key={i}>
      {i > 0 && (
        <>
          /<wbr />
        </>
      )}
      <span className="scope-segment">{part}</span>
    </Fragment>
  ))
}

interface TreeProps {
  items: ChildScope[]
  known: ReadonlySet<string>
  expanded: ReadonlySet<string>
  onToggle: (path: string) => void
  created: string | null
  rowId: (path: string) => string
  /** The scope the add field is open inside, and that field. */
  picked?: string | null
  form?: ReactNode
  /** Rows can be opened to add inside them when given; otherwise read-only. */
  onPick?: (item: ChildScope) => void
  depth?: number
}

/** Scopes as an expandable tree: each level is read from the registry when opened. */
function ScopeTree({
  items,
  known,
  expanded,
  onToggle,
  created,
  rowId,
  picked = null,
  form = null,
  onPick,
  depth = 0,
}: TreeProps) {
  const list = useRef<HTMLUListElement>(null)

  // The new scope may sit below the fold of a long list.
  useEffect(() => {
    if (created && depth === 0)
      list.current?.querySelector('[data-new]')?.scrollIntoView?.({ block: 'nearest' })
  }, [created, depth])

  return (
    <ul
      className={depth === 0 ? 'scope-tree' : 'scope-tree-group'}
      ref={depth === 0 ? list : undefined}
    >
      {items.map((item) => {
        const open = expanded.has(item.path)
        const isNew = item.path === created
        const name = (
          <>
            <span className="mono scope-leaf">{item.name}</span>
            {item.nested > 0 && (
              <span className="scope-count">
                {item.nested}
                <span className="visually-hidden">
                  {' '}
                  sub-scope{item.nested === 1 ? '' : 's'}
                </span>
              </span>
            )}
            {isNew && (
              <span className="tag" data-tone="good">
                new
              </span>
            )}
          </>
        )
        return (
          <li key={item.path} data-new={isNew ? '' : undefined}>
            <div className="scope-row" style={{ paddingLeft: depth * 16 }}>
              {item.nested > 0 ? (
                <button
                  type="button"
                  className="scope-twisty"
                  aria-expanded={open}
                  aria-label={`${open ? 'Hide' : 'Show'} what's inside ${item.name}`}
                  onClick={() => onToggle(item.path)}
                >
                  <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
                    <path
                      d="M6 4l4 4-4 4"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </button>
              ) : (
                <span className="scope-twisty-space" aria-hidden="true" />
              )}
              {onPick ? (
                <button
                  type="button"
                  id={rowId(item.path)}
                  className="scope-pick"
                  title={item.path}
                  aria-pressed={picked === item.path}
                  aria-label={`${item.name}: add a sub-scope inside`}
                  onClick={() => onPick(item)}
                >
                  {name}
                </button>
              ) : (
                <span className="scope-pick" title={item.path}>
                  {name}
                </span>
              )}
            </div>
            {picked === item.path && (
              <div className="scope-row-form" style={{ marginLeft: depth * 16 + 22 }}>
                {form}
              </div>
            )}
            {open && (
              <ScopeTree
                items={childScopes(item.path, known)}
                known={known}
                expanded={expanded}
                onToggle={onToggle}
                created={created}
                rowId={rowId}
                picked={picked}
                form={form}
                onPick={onPick}
                depth={depth + 1}
              />
            )}
          </li>
        )
      })}
    </ul>
  )
}
