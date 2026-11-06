import {
  Suspense,
  lazy,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import type { Me } from '@/api/auth'
import { brainApi, type BrainApi, type BrainResponse } from '@/api/brain'
import { ownScope, spaceName } from '@/components/ask/layers'
import {
  NO_FILTERS,
  ORIGINS,
  applyFilters,
  countKinds,
  distinct,
  facets,
  parseDate,
  isRecord,
  UNSCOPED_KINDS,
  toRows,
  type ActionRow,
  type DocumentRow,
  type InstructionRow,
  type BrainFilters,
  type BrainRow,
  type ChunkRow,
  type Kind,
  type Origin,
  type RecordRow,
  type UnknownRow,
  type Since,
  type SortBy,
} from '@/components/brain/filter'
import { isAbort, messageOf } from '@/components/capture/format'
import HeaderSlot from '@/components/HeaderSlot'
import ScopePicker from '@/components/ScopePicker'
import { TagEditor, VctCoverageView, VctTags } from '@/components/vct/Vct'
import type { VctApi } from '@/api/vct'
import { useHashSubRoute } from '@/hooks/useHashRoute'
import '@/pages/brain.css'

// The graph pulls in reagraph and three.js: loaded only when someone opens it.
const BrainGraph = lazy(() => import('@/components/brain/graph/BrainGraph'))

/**
 * Views of the same memory: #/brain/list (default), #/brain/graph, and
 * #/brain/vct for value-chain coverage and facts without a goal.
 */
const VIEWS = ['list', 'graph', 'vct'] as const
type View = (typeof VIEWS)[number]
const VIEW_LABELS: Record<View, string> = {
  list: 'List',
  graph: 'Graph',
  vct: 'Value chain',
}

/** The answer to one request, tagged with that request's key. */
type Result =
  | { key: string; status: 'error'; message: string }
  | { key: string; status: 'ready'; data: BrainResponse }

type Load = { status: 'loading' } | Result

interface Props {
  me: Me
  api?: BrainApi
  vctApi?: VctApi
}

const DATE = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})
const formatDate = (value: string) =>
  parseDate(value) ? DATE.format(parseDate(value)) : '—'
const TIME = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit' })
const DAY_MONTH = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' })
const DAY_MS = 24 * 60 * 60 * 1000
/** "Today, 16:02", "Yesterday, 09:10", "4 Nov, 16:02"; the year only when not this one. */
function shortDate(value: string, now = new Date()): string {
  const time = parseDate(value)
  if (!time) return '—'
  const date = new Date(time)
  const midnight = (d: Date) =>
    new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const days = Math.round((midnight(now) - midnight(date)) / DAY_MS)
  if (days === 0) return `Today, ${TIME.format(date)}`
  if (days === 1) return `Yesterday, ${TIME.format(date)}`
  if (date.getFullYear() === now.getFullYear())
    return `${DAY_MONTH.format(date)}, ${TIME.format(date)}`
  return DATE.format(date)
}
/** How many rows the list renders at a time; "Show more" adds as many again. */
const PAGE_SIZE = 150
/** A 0–1 score with two decimals, or a dash when Agent Memory gave none. */
const score = (value: number | null) => (value === null ? '—' : value.toFixed(2))
const NUMBER = new Intl.NumberFormat('en-GB')
const plural = (n: number, one: string, many = `${one}s`) =>
  `${NUMBER.format(n)} ${n === 1 ? one : many}`

interface KindOption {
  kind: Kind
  label: string
  /** The noun for the count: "3 facts". */
  one: string
}

const ALL_KINDS: KindOption = { kind: 'all', label: 'All', one: 'record' }
const KINDS: readonly KindOption[] = [
  ALL_KINDS,
  { kind: 'fact', label: 'Facts', one: 'fact' },
  { kind: 'relation', label: 'Relations', one: 'relation' },
  { kind: 'chunk', label: 'Memory chunks', one: 'memory chunk' },
  { kind: 'action', label: 'Actions', one: 'action' },
  { kind: 'unknown', label: 'Unknowns', one: 'unknown' },
  { kind: 'instruction', label: 'Instructions', one: 'instruction' },
  { kind: 'document', label: 'Documents', one: 'document' },
]

const SINCE: readonly { value: Since; label: string }[] = [
  { value: 'any', label: 'Any' },
  { value: '1d', label: 'Last 24 hours' },
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
]

const SORTS: readonly { value: SortBy; label: string }[] = [
  { value: 'latest', label: 'Latest first' },
  { value: 'oldest', label: 'Oldest first' },
  { value: 'entity', label: 'Entity A–Z' },
  { value: 'fact', label: 'Fact A–Z' },
]

/** A row's DOM id, for aria-controls and for scrolling to it. */
const domId = (rowId: string) => `brain-${rowId.replace(/[^a-z0-9]+/gi, '-')}`

/**
 * Everything memory holds, one row per fact, relation or memory chunk; a row
 * opens to show its details. The space filter is applied by the backend (it
 * only returns what the user may read); the rest filters and sorts what came back.
 */
export default function BrainPage({ me, api = brainApi, vctApi }: Props) {
  const [result, setResult] = useState<Result | null>(null)
  const own = ownScope(me.grants)
  // The page opens on the user's own space alone, until they use the Spaces menu.
  const [onOwn, setOnOwn] = useState(own !== null)
  // Spaces left out; empty means all of them, so new ones appear ticked.
  const [excluded, setExcluded] = useState<string[]>([])
  // Spaces nest (arun_das/demo sits inside arun_das): count the ones inside too.
  const [subscopes, setSubscopes] = useState(true)
  const [filters, setFilters] = useState<BrainFilters>(NO_FILTERS)
  const [open, setOpen] = useState<string | null>(null)
  // Every space seen, kept across reloads so a narrowed list can still widen.
  const [spaces, setSpaces] = useState<string[]>(own ? [own] : [])
  // A row to bring into view once it renders (after following a link to it).
  const scrollTo = useRef<string | null>(null)
  const view = useHashSubRoute(VIEWS, 'list')
  const search = useRef<HTMLInputElement>(null)
  // Whether the filter bar is pinned under the top bar, so it can draw an edge
  // between itself and the rows scrolling beneath it.
  const pinMark = useRef<HTMLDivElement>(null)
  const [pinned, setPinned] = useState(false)
  useEffect(() => {
    const mark = pinMark.current
    if (!mark || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver(
      ([entry]) => setPinned(entry ? !entry.isIntersecting : false),
      // The top bar is 65px tall: the mark passing under it means the bar stuck.
      { rootMargin: '-66px 0px 0px 0px' },
    )
    observer.observe(mark)
    return () => observer.disconnect()
  }, [])

  // "/" jumps to the search box, as in most apps with a list to sift.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== '/' || event.metaKey || event.ctrlKey || event.altKey) return
      const target = event.target as HTMLElement | null
      if (target?.closest('input, textarea, select, [contenteditable="true"]')) return
      event.preventDefault()
      search.current?.focus()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const ownOnly = onOwn && own ? [own] : null
  const chosen = ownOnly ?? spaces.filter((s) => !excluded.includes(s))
  const narrowed = ownOnly ?? (excluded.length ? chosen : [])
  // Everything deselected: nothing to fetch. (No scopes would mean "all" to the backend.)
  const none = !ownOnly && spaces.length > 0 && chosen.length === 0
  // A string key, so the fetch reruns only when the chosen spaces really change.
  const scopeKey = narrowed.join('\n')
  // Replaced values come from each entity's history: only read when asked for.
  const withReplaced = filters.showReplaced
  const requestKey = `${scopeKey}|${subscopes}|${withReplaced}`
  // Loading until the result for the current request arrives; no state is set
  // when a request starts.
  const load: Load = result?.key === requestKey ? result : { status: 'loading' }

  useEffect(() => {
    if (none) return
    const controller = new AbortController()
    const key = `${scopeKey}|${subscopes}|${withReplaced}`
    api
      .list(
        {
          scopes: scopeKey ? scopeKey.split('\n') : [],
          subscopes,
          replaced: withReplaced,
        },
        controller.signal,
      )
      .then((data) => {
        setResult({ key, status: 'ready', data })
        setSpaces((known) => distinct([...known, ...data.scopes]))
      })
      .catch((err: unknown) => {
        if (!isAbort(err)) setResult({ key, status: 'error', message: messageOf(err) })
      })
    return () => controller.abort()
  }, [api, none, scopeKey, subscopes, withReplaced])

  // After following a link to a row: scroll it into view and put focus on it.
  useEffect(() => {
    const id = scrollTo.current
    if (!id) return
    const row = document.getElementById(`${domId(id)}-row`)
    // Coming from the graph, the list renders a moment later: wait for it.
    if (!row && view !== 'list') return
    scrollTo.current = null
    row?.scrollIntoView?.({ block: 'center', behavior: 'smooth' })
    row?.focus({ preventScroll: true })
  })

  const data = load.status === 'ready' ? load.data : null
  // Memoised so the graph gets the same array until the data or filters change;
  // a new one re-runs its layout.
  const rows = useMemo(
    () =>
      data
        ? toRows(
            data.entities,
            data.chunks ?? [],
            data.actions ?? [],
            data.unknowns ?? [],
            data.instructions ?? [],
            data.documents ?? [],
          )
        : [],
    [data],
  )
  const shown = useMemo(() => applyFilters(rows, filters), [rows, filters])
  const counts = countKinds(rows, filters)
  const { types, categories } = facets(rows)
  const kind = KINDS.find((k) => k.kind === filters.kind) ?? ALL_KINDS
  // Rows of the chosen kind before any other filter: the "of N" in the count.
  const ofKind = rows.filter(
    (r) => filters.kind === 'all' || r.kind === filters.kind,
  ).length
  // Anything narrowing the list beyond the kind tab.
  const filtering =
    filters.query !== '' ||
    filters.type !== '' ||
    filters.category !== '' ||
    filters.since !== 'any'
  const byId = new Map(rows.map((row) => [row.id, row]))

  const set = <K extends keyof BrainFilters>(key: K, value: BrainFilters[K]) =>
    setFilters((current) => ({ ...current, [key]: value }))

  /** Opens a row, widening the filters first if they hide it. */
  const reveal = (id: string) => {
    if (!shown.some((row) => row.id === id)) {
      const target = byId.get(id)
      // Only turn on replaced values when the row is one; otherwise keep the choice.
      const replaced = target !== undefined && isRecord(target) && target.replaced
      setFilters({
        ...NO_FILTERS,
        sort: filters.sort,
        showReplaced: filters.showReplaced || replaced,
      })
    }
    setOpen(id)
    scrollTo.current = id
  }

  /** Back to every row of the chosen kind, keeping the order and replaced choice. */
  const clearFilters = () =>
    setFilters((current) => ({
      ...NO_FILTERS,
      kind: current.kind,
      sort: current.sort,
      showReplaced: current.showReplaced,
    }))

  // The list renders a page at a time; a new filtered list starts again at one
  // page, and a row opened from elsewhere is always rendered.
  const [paged, setPaged] = useState<{ list: readonly BrainRow[]; count: number }>({
    list: shown,
    count: PAGE_SIZE,
  })
  const openAt = open ? shown.findIndex((row) => row.id === open) : -1
  const rendered = Math.max(paged.list === shown ? paged.count : PAGE_SIZE, openAt + 1)
  const visible = shown.slice(0, rendered)

  /** From the graph: switch to the list with that row open. */
  const openInList = (id: string) => {
    window.location.hash = '#/brain/list'
    reveal(id)
  }

  // Name each space as Ask does when the user holds it; otherwise by its path.
  const options = spaces.map((path) => {
    const grant = me.grants.find((g) => g.scope_path === path)
    const name = grant ? spaceName(grant) : path.split('/').slice(-2).join('/')
    return { id: path, name, detail: path }
  })

  return (
    <main className="page brain-page">
      <div className="page-head brain-head">
        <div className="brain-head-top">
          <h1>Brain</h1>
          <nav className="brain-views" aria-label="Brain view">
            {VIEWS.map((v) => (
              <a
                key={v}
                href={`#/brain/${v}`}
                aria-current={v === view ? 'page' : undefined}
              >
                {v === 'list' ? (
                  <ListIcon />
                ) : v === 'graph' ? (
                  <GraphIcon />
                ) : (
                  <ChainIcon />
                )}
                {VIEW_LABELS[v]}
              </a>
            ))}
          </nav>
        </div>
        <p>
          Everything memory holds in the spaces you can read: facts and relations, the
          memory chunks they came from, the actions it recorded and what it couldn’t
          settle, plus the rules it follows and the documents it was given. Open a row to
          see where and when it was saved.
        </p>
      </div>

      {options.length > 1 && (
        <HeaderSlot>
          <ScopePicker
            multiple
            label="Spaces"
            allLabel="All spaces"
            options={options}
            value={chosen}
            onChange={(ids) => {
              setOnOwn(false)
              setExcluded(spaces.filter((s) => !ids.includes(s)))
            }}
          />
          {narrowed.length > 0 && (
            // Sub-spaces show by default; this box is for leaving them out.
            <label
              className="brain-subspaces"
              title="Show only memory saved in the spaces picked, not in spaces inside them (e.g. arun_das/demo)"
            >
              <input
                type="checkbox"
                checked={!subscopes}
                onChange={(e) => setSubscopes(!e.target.checked)}
              />
              Exclude sub-spaces
            </label>
          )}
        </HeaderSlot>
      )}

      <div ref={pinMark} aria-hidden="true" />
      <section
        className="brain-bar"
        aria-label="Filters"
        data-pinned={pinned ? '' : undefined}
      >
        <FilterChip
          label="Show"
          value={filters.kind}
          idle="all"
          options={KINDS.map((k) => ({
            value: k.kind,
            label: data ? `${k.label} (${NUMBER.format(counts[k.kind])})` : k.label,
          }))}
          onChange={(value) => set('kind', value as Kind)}
        />

        <label className="brain-search">
          <SearchIcon />
          <input
            ref={search}
            type="search"
            aria-label="Search"
            aria-keyshortcuts="/"
            value={filters.query}
            placeholder="Search memory"
            onChange={(e) => set('query', e.target.value)}
          />
          {!filters.query && (
            <kbd className="brain-kbd" aria-hidden="true">
              /
            </kbd>
          )}
        </label>

        <FilterChip
          label="Type"
          name="Entity type"
          value={filters.type}
          idle=""
          options={[{ value: '', label: 'Any' }, ...types.map(asOption)]}
          onChange={(value) => set('type', value)}
        />
        <FilterChip
          label="Category"
          value={filters.category}
          idle=""
          options={[{ value: '', label: 'Any' }, ...categories.map(asOption)]}
          onChange={(value) => set('category', value)}
        />
        <FilterChip
          label="Saved"
          value={filters.since}
          idle="any"
          options={SINCE}
          onChange={(value) => set('since', value as Since)}
        />
        <FilterChip
          label="Source"
          value={filters.origin}
          idle=""
          options={[{ value: '', label: 'Any' }, ...ORIGINS]}
          onChange={(value) => set('origin', value as Origin | '')}
        />
        {view === 'list' && (
          <FilterChip
            label="Sort"
            value={filters.sort}
            idle={filters.sort}
            options={SORTS}
            onChange={(value) => set('sort', value as SortBy)}
          />
        )}
        {(filters.kind === 'all' || filters.kind === 'fact') && (
          <ToggleChip
            checked={filters.showReplaced}
            onChange={(checked) => set('showReplaced', checked)}
            title="Also show older values that a newer one replaced, e.g. a lead time of 10 days later replaced by 18"
          >
            Old values
          </ToggleChip>
        )}

        <div className="brain-bar-end">
          {data && (
            <p className="brain-count" aria-live="polite">
              {shown.length < ofKind ? (
                // Narrowed: "12 of 139", short so the row stays on one line; the
                // noun is still there for screen readers.
                <>
                  {NUMBER.format(shown.length)}
                  <span className="visually-hidden">
                    {' '}
                    {shown.length === 1 ? kind.one : `${kind.one}s`}
                  </span>
                  <span className="brain-muted"> of {NUMBER.format(ofKind)}</span>
                </>
              ) : (
                plural(shown.length, kind.one)
              )}
            </p>
          )}
          {filtering && (
            <button
              type="button"
              className="brain-clear"
              aria-label="Clear filters"
              onClick={clearFilters}
            >
              Clear
            </button>
          )}
        </div>
      </section>

      {data && UNSCOPED_KINDS.has(filters.kind) && (
        <p className="note brain-note">
          {filters.kind === 'instruction'
            ? 'Instructions belong to no space: memory follows them in every answer, so they show whatever spaces are picked. Agent Memory keeps no date for them.'
            : "Documents belong to no space, so they show whatever spaces are picked. Only admins see them, since there's no space to check access against."}
        </p>
      )}
      {data && data.replaced_missing > 0 && (
        <output className="note brain-note">
          The history of {plural(data.replaced_missing, 'entity', 'entities')} couldn't be
          read this time, so some old values are missing. Reload the page to try again.
        </output>
      )}
      {data && data.chunks_missing > 0 && (
        <output className="note brain-note">
          The text of {plural(data.chunks_missing, 'capture')} couldn't be read this time,
          so some memory chunks are missing. Reload the page to try again.
        </output>
      )}

      {none && (
        <p className="empty">
          No spaces selected. Pick at least one in the Spaces menu to see what memory
          holds.
        </p>
      )}
      {!none && load.status === 'loading' && <BrainSkeleton />}
      {!none && load.status === 'error' && (
        <p className="error" role="alert">
          Could not load memory: {load.message}
        </p>
      )}
      {!none && load.status === 'ready' && view === 'vct' && (
        <VctCoverageView
          api={vctApi}
          facts={rows
            .filter((r): r is RecordRow => r.kind === 'fact' && !r.replaced)
            .map((r) => ({
              id: r.record_id,
              entity: r.entity,
              key: r.key,
              value: r.value,
              tags: r.vct,
              tagged: r.vct_tagged ?? false,
            }))}
        />
      )}
      {!none && load.status === 'ready' && view === 'graph' && (
        <Suspense fallback={<p className="brain-muted">Loading the graph…</p>}>
          <BrainGraph rows={shown} onOpen={openInList} />
        </Suspense>
      )}
      {!none &&
        load.status === 'ready' &&
        view === 'list' &&
        (shown.length === 0 ? (
          <div className="empty brain-empty">
            {rows.length ? (
              <>
                <p>Nothing matches these filters.</p>
                <button type="button" className="btn-secondary" onClick={clearFilters}>
                  Clear filters
                </button>
              </>
            ) : (
              <>
                <p>Nothing saved in {ownOnly ? 'your space' : 'these spaces'} yet.</p>
                <div className="brain-empty-actions">
                  <a className="btn-secondary" href="#/capture">
                    Capture something
                  </a>
                  {narrowed.length > 0 && spaces.length > 1 && (
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => {
                        setOnOwn(false)
                        setExcluded([])
                      }}
                    >
                      Look in all spaces
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        ) : (
          <>
            <ul className="brain-list">
              {visible.map((row) => (
                <BrainItem
                  key={row.id}
                  row={row}
                  open={open === row.id}
                  byId={byId}
                  onToggle={() =>
                    setOpen((current) => (current === row.id ? null : row.id))
                  }
                  onReveal={reveal}
                  vctApi={vctApi}
                />
              ))}
            </ul>
            {visible.length < shown.length && (
              <div className="brain-more">
                <p className="brain-muted">
                  Showing {NUMBER.format(visible.length)} of {NUMBER.format(shown.length)}
                </p>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setPaged({ list: shown, count: rendered + PAGE_SIZE })}
                >
                  Show {NUMBER.format(Math.min(PAGE_SIZE, shown.length - visible.length))}{' '}
                  more
                </button>
                <button
                  type="button"
                  className="brain-clear"
                  onClick={() => setPaged({ list: shown, count: shown.length })}
                >
                  Show all
                </button>
              </div>
            )}
          </>
        ))}
    </main>
  )
}

const asOption = (value: string) => ({ value, label: value })

/**
 * A compact filter as a chip, "Type  Any ▾". The native select covers the
 * whole chip, so a click anywhere opens it and the keyboard works as usual.
 * `idle` is the value that means "not filtering"; any other is highlighted.
 */
function FilterChip({
  label,
  name = label,
  value,
  idle,
  options,
  onChange,
}: {
  label: string
  /** The select's accessible name, when it says more than the visible label. */
  name?: string
  value: string
  idle: string
  options: readonly { value: string; label: string }[]
  onChange: (value: string) => void
}) {
  const current = options.find((o) => o.value === value)?.label ?? value
  return (
    <span className="brain-chip" data-active={value !== idle ? '' : undefined}>
      <span className="brain-chip-label" aria-hidden="true">
        {label}
      </span>
      <span className="brain-chip-value" aria-hidden="true">
        {current}
      </span>
      <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
        <path
          d="M4 6l4 4 4-4"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <select aria-label={name} value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </span>
  )
}

/** An on/off filter as a chip, with a real checkbox inside. */
function ToggleChip({
  checked,
  onChange,
  children,
  title,
}: {
  checked: boolean
  onChange: (checked: boolean) => void
  children: ReactNode
  /** What the toggle does, on hover. */
  title?: string
}) {
  return (
    <label
      className="brain-chip brain-toggle"
      data-active={checked ? '' : undefined}
      title={title}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      {children}
    </label>
  )
}

function ListIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
      <path
        d="M5.5 4h8M5.5 8h8M5.5 12h8M2.5 4h.01M2.5 8h.01M2.5 12h.01"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  )
}

function GraphIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none">
      <path
        d="M4.5 5l7 1.5M4.5 5l2 6.5M11.5 6.5l-5 5"
        stroke="currentColor"
        strokeWidth="1.3"
      />
      <circle cx="4" cy="4.5" r="2" fill="currentColor" />
      <circle cx="12" cy="6.5" r="2" fill="currentColor" />
      <circle cx="6.5" cy="12" r="2" fill="currentColor" />
    </svg>
  )
}

/** Three stops on a line: the value chain. */
function ChainIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none">
      <path d="M2 8h12" stroke="currentColor" strokeWidth="1.3" />
      <circle cx="3" cy="8" r="2" fill="currentColor" />
      <circle cx="8" cy="8" r="2" fill="currentColor" />
      <circle cx="13" cy="8" r="2" fill="currentColor" />
    </svg>
  )
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      <circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <path
        d="M10.5 10.5L14 14"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  )
}

/** Placeholder rows while memory loads, shaped like the list that will replace them. */
function BrainSkeleton() {
  return (
    <ul
      className="brain-list brain-skeleton"
      aria-busy="true"
      aria-label="Loading memory"
    >
      {[62, 48, 71, 40, 55, 66].map((width, i) => (
        <li key={i} className="brain-fact">
          <span className="brain-skeleton-bar" style={{ width: `${width}%` }} />
        </li>
      ))}
      <li className="brain-skeleton-note">
        Reading memory… a large space can take up to 20 seconds.
      </li>
    </ul>
  )
}

interface ItemProps {
  row: BrainRow
  open: boolean
  byId: ReadonlyMap<string, BrainRow>
  onToggle: () => void
  onReveal: (id: string) => void
  vctApi?: VctApi
}

/** One row of the list: a fact, a relation or a memory chunk. */
function BrainItem({ row, open, byId, onToggle, onReveal, vctApi }: ItemProps) {
  const panelId = domId(row.id)
  const chunk = row.kind === 'chunk'
  const replaced = isRecord(row) && row.replaced
  return (
    <li
      className="brain-fact"
      data-kind={row.kind}
      data-open={open}
      data-replaced={replaced}
    >
      <button
        type="button"
        id={`${panelId}-row`}
        className="brain-row"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={onToggle}
      >
        <span className="brain-caret" aria-hidden="true" />
        {row.kind === 'chunk' ? (
          <ChunkLine row={row} />
        ) : row.kind === 'action' ? (
          <ActionLine row={row} />
        ) : row.kind === 'unknown' ? (
          <UnknownLine row={row} />
        ) : row.kind === 'instruction' ? (
          <InstructionLine row={row} />
        ) : row.kind === 'document' ? (
          <DocumentLine row={row} />
        ) : (
          <RecordLine row={row} />
        )}
        <span className="brain-tags">
          {row.kind === 'relation' && <span className="tag">relation</span>}
          {chunk && row.role && row.role !== 'user' && (
            <span className="tag">{row.role}</span>
          )}
          {chunk && <span className="tag">chunk</span>}
          {row.kind === 'action' && <span className="tag">action</span>}
          {row.kind === 'unknown' && (
            <span className="tag" data-tone={row.resolved ? undefined : 'note'}>
              {row.resolved ? 'resolved' : 'open'}
            </span>
          )}
          {row.kind === 'instruction' && <span className="tag">instruction</span>}
          {row.kind === 'document' && (
            <span className="tag" data-tone={STATUS_TONE[row.status]}>
              {row.status || 'document'}
            </span>
          )}
          {replaced && (
            <span className="tag" data-tone="note">
              replaced
            </span>
          )}
        </span>
        <time
          className="brain-date"
          dateTime={row.created_at}
          title={formatDate(row.created_at)}
        >
          {shortDate(row.created_at)}
        </time>
      </button>
      {open &&
        (row.kind === 'chunk' ? (
          <ChunkDetail id={panelId} row={row} byId={byId} onReveal={onReveal} />
        ) : row.kind === 'action' ? (
          <ActionDetail id={panelId} row={row} onReveal={onReveal} />
        ) : row.kind === 'unknown' ? (
          <UnknownDetail id={panelId} row={row} />
        ) : row.kind === 'instruction' ? (
          <InstructionDetail id={panelId} row={row} />
        ) : row.kind === 'document' ? (
          <DocumentDetail id={panelId} row={row} />
        ) : (
          <RecordDetail id={panelId} row={row} onReveal={onReveal} vctApi={vctApi} />
        ))}
    </li>
  )
}

/** "actor · verb → object" on one line, as facts read. */
function ActionLine({ row }: { row: ActionRow }) {
  return (
    <span className="brain-text">
      <span className="brain-entity-name">{row.actor}</span>
      <span className="brain-sep" aria-hidden="true">
        ·
      </span>
      <span className="mono brain-key">{row.verb}</span>
      {row.object && (
        <>
          <span className="brain-sep" aria-hidden="true">
            →
          </span>
          <span className="brain-value">{row.object}</span>
        </>
      )}
    </span>
  )
}

/** What memory couldn't settle, in its own words. */
function UnknownLine({ row }: { row: UnknownRow }) {
  return (
    <span className="brain-text">
      <span className="brain-chunk-line">{row.about}</span>
    </span>
  )
}

/** "label · description", as a fact reads "key = value". */
function InstructionLine({ row }: { row: InstructionRow }) {
  return (
    <span className="brain-text">
      <span className="mono brain-key">{row.label}</span>
      <span className="brain-sep" aria-hidden="true">
        ·
      </span>
      <span className="brain-value">{row.description}</span>
    </span>
  )
}

/** The document's title, then its file name when that says something more. */
function DocumentLine({ row }: { row: DocumentRow }) {
  return (
    <span className="brain-text">
      <span className="brain-entity-name">{row.title || row.file_name}</span>
      {row.file_name && row.file_name !== row.title && (
        <>
          <span className="brain-sep" aria-hidden="true">
            ·
          </span>
          <span className="mono brain-key">{row.file_name}</span>
        </>
      )}
    </span>
  )
}

/** Tag tone per document status: done reads good, failed warns, the rest wait. */
const STATUS_TONE: Record<string, string | undefined> = {
  done: 'good',
  completed: 'good',
  failed: 'warn',
  queued: 'note',
  processing: 'note',
}

const STATUS_TEXT: Record<string, string> = {
  queued:
    'Queued: waiting for Agent Memory to read it. Nothing has been taken from it yet.',
  processing: 'Being read now.',
  done: 'Read: its memories are in.',
  completed: 'Read: its memories are in.',
  failed: 'Reading failed.',
}

function fileSize(bytes: number | null): string {
  if (bytes === null) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function InstructionDetail({ id, row }: { id: string; row: InstructionRow }) {
  return (
    <div id={id} className="brain-detail brain-record">
      <dl className="brain-detail-grid">
        <dt>Rule</dt>
        <dd>{row.description || '—'}</dd>
        <dt>Label</dt>
        <dd className="mono">{row.label}</dd>
        <dt>Applies to</dt>
        <dd>Every answer, in every space</dd>
        <dt>ID</dt>
        <dd className="mono">{row.record_id}</dd>
      </dl>
    </div>
  )
}

function DocumentDetail({ id, row }: { id: string; row: DocumentRow }) {
  return (
    <div id={id} className="brain-detail brain-record">
      <dl className="brain-detail-grid">
        <dt>Title</dt>
        <dd>{row.title || '—'}</dd>
        <dt>File</dt>
        <dd>
          <span className="mono">{row.file_name || '—'}</span>
          <span className="brain-muted">
            {' '}
            ({[row.mime_type, fileSize(row.size_bytes)].filter(Boolean).join(', ')})
          </span>
        </dd>
        <dt>Status</dt>
        <dd>
          {STATUS_TEXT[row.status] ?? row.status ?? '—'}
          {row.error && <span className="brain-muted"> {row.error}</span>}
        </dd>
        <dt>Uploaded</dt>
        <dd>{formatDate(row.created_at)}</dd>
        <dt>Read</dt>
        <dd>{row.processed_at ? formatDate(row.processed_at) : 'Not yet'}</dd>
        <dt>ID</dt>
        <dd className="mono">{row.record_id}</dd>
      </dl>
    </div>
  )
}

const ORIGIN_LABEL = Object.fromEntries(ORIGINS.map((o) => [o.value, o.label]))

function ActionDetail({
  id,
  row,
  onReveal,
}: {
  id: string
  row: ActionRow
  onReveal: (id: string) => void
}) {
  const chunk = row.chunk
  return (
    <div id={id} className="brain-detail brain-record">
      <dl className="brain-detail-grid">
        <dt>Summary</dt>
        <dd>{row.summary ?? '—'}</dd>
        <dt>Who</dt>
        <dd>
          {row.actor} <span className="tag">{row.actor_type}</span>
        </dd>
        <dt>Did</dt>
        <dd className="mono">{row.verb}</dd>
        <dt>To what</dt>
        <dd>{row.object ?? '—'}</dd>
        <dt>When</dt>
        <dd>{row.occurred_at ? formatDate(row.occurred_at) : 'Not said'}</dd>
        <dt>Category</dt>
        <dd>{row.category || '—'}</dd>
        <dt>Space</dt>
        <dd>
          <span className="mono">{row.scopes.join(', ') || '—'}</span>
          <span className="brain-muted"> (from the capture it came from)</span>
        </dd>
        <dt>Saved</dt>
        <dd>{formatDate(row.created_at)}</dd>
        <dt>Taken from</dt>
        <dd>
          {chunk ? (
            <button type="button" className="brain-link" onClick={() => onReveal(chunk)}>
              Show the memory chunk
            </button>
          ) : (
            '—'
          )}
        </dd>
      </dl>
      <details className="brain-more-details">
        <summary>More details</summary>
        <dl className="brain-detail-grid">
          <dt>Source</dt>
          <dd>{row.origin ? ORIGIN_LABEL[row.origin] : (row.source?.kind ?? '—')}</dd>
          <dt>Confidence</dt>
          <dd>{score(row.confidence)}</dd>
          <dt>Source ref</dt>
          <dd className="mono">{row.source?.ref ?? '—'}</dd>
          <dt>Session</dt>
          <dd className="mono">{row.source?.session_id ?? '—'}</dd>
          <dt>ID</dt>
          <dd className="mono">{row.record_id}</dd>
        </dl>
      </details>
    </div>
  )
}

function UnknownDetail({ id, row }: { id: string; row: UnknownRow }) {
  return (
    <div id={id} className="brain-detail brain-record">
      <dl className="brain-detail-grid">
        <dt>About</dt>
        <dd>{row.about}</dd>
        <dt>Why</dt>
        <dd>{row.reason || '—'}</dd>
        <dt>Concerns</dt>
        <dd>
          {row.entity ?? '—'}
          {row.entity_type && <span className="tag">{row.entity_type}</span>}
          {row.key && (
            <>
              {' '}
              · <span className="mono">{row.key}</span>
            </>
          )}
        </dd>
        <dt>Status</dt>
        <dd>
          {row.resolved
            ? 'Resolved'
            : row.resolvable
              ? 'Open: more input could settle it'
              : 'Open: memory can’t settle this by itself'}
        </dd>
        <dt>Space</dt>
        <dd className="mono">{row.scopes.join(', ') || '—'}</dd>
        <dt>Saved</dt>
        <dd>{formatDate(row.created_at)}</dd>
        <dt>Labels</dt>
        <dd>
          {row.labels.length
            ? row.labels.map((label) => (
                <span key={label} className="tag brain-label">
                  {label}
                </span>
              ))
            : '—'}
        </dd>
        <dt>ID</dt>
        <dd className="mono">{row.record_id}</dd>
      </dl>
    </div>
  )
}

/** "entity · key = value" on one line. */
function RecordLine({ row }: { row: RecordRow }) {
  return (
    <span className="brain-text">
      <span className="brain-entity-name">{row.entity}</span>
      <span className="brain-sep" aria-hidden="true">
        ·
      </span>
      <span className="mono brain-key">{row.key}</span>
      <span className="brain-sep" aria-hidden="true">
        {row.kind === 'relation' ? '→' : '='}
      </span>
      <span className="brain-value">{row.value}</span>
      {row.kind === 'fact' && !row.replaced && (
        <VctTags tags={row.vct} tagged={row.vct_tagged ?? false} />
      )}
    </span>
  )
}

/** The start of a chunk's text, on one line; the details show all of it. */
function ChunkLine({ row }: { row: ChunkRow }) {
  return (
    <span className="brain-text">
      <span className="brain-chunk-line">
        {row.text.replace(/\s+/g, ' ').slice(0, 280)}
      </span>
    </span>
  )
}

function RecordDetail({
  id,
  row,
  onReveal,
  vctApi,
}: {
  id: string
  row: RecordRow
  onReveal: (id: string) => void
  vctApi?: VctApi
}) {
  const relation = row.kind === 'relation'
  const chunk = row.chunk
  return (
    <div id={id} className="brain-detail brain-record">
      {!relation && !row.replaced && (
        <section className="brain-vct" aria-label="Value chain tags">
          <h3 className="brain-vct-heading">Value chain</h3>
          <TagEditor factId={row.record_id} api={vctApi} />
        </section>
      )}
      <dl className="brain-detail-grid">
        <dt>Entity</dt>
        <dd>
          {row.entity} <span className="tag">{row.entity_type}</span>
        </dd>
        <dt>{relation ? 'Relation' : 'Fact'}</dt>
        <dd className="mono">{row.key}</dd>
        <dt>{relation ? 'Related to' : 'Value'}</dt>
        <dd>{row.value}</dd>
        <dt>Summary</dt>
        <dd>{row.summary ?? '—'}</dd>
        <dt>Labels</dt>
        <dd>
          {row.labels.length
            ? row.labels.map((label) => (
                <span key={label} className="tag brain-label">
                  {label}
                </span>
              ))
            : '—'}
        </dd>
        <dt>Category</dt>
        <dd>{row.category || '—'}</dd>
        <dt>Space</dt>
        <dd className="mono">{row.scopes.join(', ') || '—'}</dd>
        <dt>Saved</dt>
        <dd>{formatDate(row.created_at)}</dd>
        <dt>Status</dt>
        <dd>{row.replaced ? 'Replaced by a newer value' : 'Current'}</dd>
        <dt>Taken from</dt>
        <dd>
          {chunk ? (
            <button type="button" className="brain-link" onClick={() => onReveal(chunk)}>
              Show the memory chunk
            </button>
          ) : (
            '—'
          )}
        </dd>
      </dl>
      <details className="brain-more-details">
        <summary>More details</summary>
        <dl className="brain-detail-grid">
          <dt>Confidence</dt>
          <dd>{score(row.confidence)}</dd>
          <dt>Importance</dt>
          <dd>{score(row.importance)}</dd>
          <dt>Valid from</dt>
          <dd>{row.valid_from ? formatDate(row.valid_from) : '—'}</dd>
          <dt>Valid until</dt>
          <dd>{row.valid_until ? formatDate(row.valid_until) : '—'}</dd>
          <dt>Source</dt>
          <dd>{row.source?.kind ?? '—'}</dd>
          <dt>Source ref</dt>
          <dd className="mono">{row.source?.ref ?? '—'}</dd>
          <dt>Session</dt>
          <dd className="mono">{row.source?.session_id ?? '—'}</dd>
          <dt>Source trust</dt>
          <dd>{score(row.source?.trust ?? null)}</dd>
          <dt>Replaces</dt>
          <dd className="mono">{row.supersedes ?? '—'}</dd>
          <dt>Replaced by</dt>
          <dd className="mono">{row.superseded_by ?? '—'}</dd>
          <dt>Entity ref</dt>
          <dd className="mono">{row.entity_ref ?? '—'}</dd>
          {relation && (
            <>
              <dt>Related ref</dt>
              <dd className="mono">{row.value_ref ?? '—'}</dd>
            </>
          )}
          <dt>ID</dt>
          <dd className="mono">{row.record_id}</dd>
        </dl>
      </details>
    </div>
  )
}

function ChunkDetail({
  id,
  row,
  byId,
  onReveal,
}: {
  id: string
  row: ChunkRow
  byId: ReadonlyMap<string, BrainRow>
  onReveal: (id: string) => void
}) {
  const heading = useId()
  const derived = row.derived.flatMap((rowId) => {
    const found = byId.get(rowId)
    return found && isRecord(found) ? [found] : []
  })
  return (
    <div id={id} className="brain-detail brain-chunk">
      <p className="brain-chunk-text">{row.text}</p>
      <section className="brain-derived" aria-labelledby={heading}>
        <h3 id={heading}>
          Extracted from this text{' '}
          <span className="brain-muted">({NUMBER.format(derived.length)})</span>
        </h3>
        {derived.length ? (
          <ul>
            {derived.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className="brain-link"
                  onClick={() => onReveal(item.id)}
                >
                  {item.entity} · <span className="mono">{item.key}</span>{' '}
                  {item.kind === 'relation' ? '→' : '='} {item.value}
                </button>
                {item.replaced && (
                  <span className="tag" data-tone="note">
                    replaced
                  </span>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="brain-muted">
            Nothing was extracted from this text on its own; Ask can still find it by
            meaning.
          </p>
        )}
      </section>
      <dl className="brain-detail-grid">
        <dt>Role</dt>
        <dd>{row.role || '—'}</dd>
        <dt>Space</dt>
        <dd>
          <span className="mono">{row.scopes.join(', ') || '—'}</span>
          <span className="brain-muted"> (from the facts it produced)</span>
        </dd>
        <dt>Saved</dt>
        <dd>{formatDate(row.created_at)}</dd>
        <dt>Session</dt>
        <dd className="mono">{row.session_id}</dd>
        <dt>Turn ID</dt>
        <dd className="mono">{row.record_id}</dd>
      </dl>
    </div>
  )
}
