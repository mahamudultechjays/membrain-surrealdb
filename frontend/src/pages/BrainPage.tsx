import { useEffect, useState } from 'react'
import type { Me } from '@/api/auth'
import { brainApi, type BrainApi, type BrainResponse } from '@/api/brain'
import { spaceName } from '@/components/ask/layers'
import {
  NO_FILTERS,
  applyFilters,
  distinct,
  parseDate,
  toRows,
  type BrainFilters,
  type BrainRow,
  type Kind,
  type Since,
  type SortBy,
} from '@/components/brain/filter'
import { isAbort, messageOf } from '@/components/capture/format'
import HeaderSlot from '@/components/HeaderSlot'
import ScopePicker from '@/components/ScopePicker'
import '@/pages/brain.css'

/** The answer to one request, tagged with that request's key. */
type Result =
  | { key: string; status: 'error'; message: string }
  | { key: string; status: 'ready'; data: BrainResponse }

type Load = { status: 'loading' } | Result

interface Props {
  me: Me
  api?: BrainApi
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
/** A 0–1 score with two decimals, or a dash when Agent Memory gave none. */
const score = (value: number | null) => (value === null ? '—' : value.toFixed(2))
const plural = (n: number, one: string, many = `${one}s`) =>
  `${n} ${n === 1 ? one : many}`

/**
 * Everything memory holds, one fact per row; a row opens to show its details.
 * The space filter is applied by the backend (it only returns what the user
 * may read); the rest filters and sorts what came back.
 */
export default function BrainPage({ me, api = brainApi }: Props) {
  const [result, setResult] = useState<Result | null>(null)
  // Spaces left out; empty means all of them, so new ones appear ticked.
  const [excluded, setExcluded] = useState<string[]>([])
  const [subscopes, setSubscopes] = useState(false)
  const [filters, setFilters] = useState<BrainFilters>(NO_FILTERS)
  const [open, setOpen] = useState<string | null>(null)
  // Every space seen, kept across reloads so a narrowed list can still widen.
  const [spaces, setSpaces] = useState<string[]>([])

  const chosen = spaces.filter((s) => !excluded.includes(s))
  const narrowed = excluded.length ? chosen : []
  // Everything deselected: nothing to fetch. (No scopes would mean "all" to the backend.)
  const none = spaces.length > 0 && chosen.length === 0
  // A string key, so the fetch reruns only when the chosen spaces really change.
  const scopeKey = narrowed.join('\n')
  const requestKey = `${scopeKey}|${subscopes}`
  // Loading until the result for the current request arrives; no state is set
  // when a request starts.
  const load: Load = result?.key === requestKey ? result : { status: 'loading' }

  useEffect(() => {
    if (none) return
    const controller = new AbortController()
    const key = `${scopeKey}|${subscopes}`
    api
      .list(
        { scopes: scopeKey ? scopeKey.split('\n') : [], subscopes },
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
  }, [api, none, scopeKey, subscopes])

  const rows = load.status === 'ready' ? toRows(load.data.entities) : []
  const shown = applyFilters(rows, filters)
  const types = distinct(rows.map((r) => r.entity_type))
  const categories = distinct(rows.map((r) => r.category))
  const filtering =
    filters.query ||
    filters.kind !== 'all' ||
    filters.type ||
    filters.category ||
    filters.since !== 'any'

  const set = <K extends keyof BrainFilters>(key: K, value: BrainFilters[K]) =>
    setFilters((current) => ({ ...current, [key]: value }))

  // Name each space as Ask does when the user holds it; otherwise by its path.
  const options = spaces.map((path) => {
    const grant = me.grants.find((g) => g.scope_path === path)
    const name = grant ? spaceName(grant) : path.split('/').slice(-2).join('/')
    return { id: path, name, detail: path }
  })

  return (
    <main className="page brain-page">
      <div className="page-head">
        <h1>Brain</h1>
        <p>
          Every fact memory holds in the spaces you can read. Open a fact to see where and
          when it was saved.
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
            onChange={(ids) => setExcluded(spaces.filter((s) => !ids.includes(s)))}
          />
        </HeaderSlot>
      )}

      <section className="panel brain-tools" aria-label="Filters">
        <label className="brain-search">
          <span>Search</span>
          <input
            type="search"
            value={filters.query}
            placeholder="Entity, fact or value"
            onChange={(e) => set('query', e.target.value)}
          />
        </label>
        <label>
          <span>Show</span>
          <select
            value={filters.kind}
            onChange={(e) => set('kind', e.target.value as Kind)}
          >
            <option value="all">Facts and relations</option>
            <option value="fact">Facts only</option>
            <option value="relation">Relations only</option>
          </select>
        </label>
        <label>
          <span>Entity type</span>
          <select value={filters.type} onChange={(e) => set('type', e.target.value)}>
            <option value="">All types</option>
            {types.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Category</span>
          <select
            value={filters.category}
            onChange={(e) => set('category', e.target.value)}
          >
            <option value="">All categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Saved</span>
          <select
            value={filters.since}
            onChange={(e) => set('since', e.target.value as Since)}
          >
            <option value="any">Any time</option>
            <option value="1d">Last 24 hours</option>
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
          </select>
        </label>
        <label>
          <span>Sort</span>
          <select
            value={filters.sort}
            onChange={(e) => set('sort', e.target.value as SortBy)}
          >
            <option value="latest">Latest first</option>
            <option value="oldest">Oldest first</option>
            <option value="entity">Entity A–Z</option>
            <option value="fact">Fact A–Z</option>
          </select>
        </label>
        <div className="brain-checks">
          <label className="brain-check">
            <input
              type="checkbox"
              checked={filters.showReplaced}
              onChange={(e) => set('showReplaced', e.target.checked)}
            />
            Show replaced values
          </label>
          {narrowed.length > 0 && (
            <label className="brain-check">
              <input
                type="checkbox"
                checked={subscopes}
                onChange={(e) => setSubscopes(e.target.checked)}
              />
              Include sub-spaces
            </label>
          )}
        </div>
      </section>

      {none && (
        <p className="empty">
          No spaces selected. Pick at least one in the Spaces menu to see its facts.
        </p>
      )}
      {!none && load.status === 'loading' && (
        <p className="brain-muted">Loading memory…</p>
      )}
      {!none && load.status === 'error' && (
        <p className="error" role="alert">
          Could not load memory: {load.message}
        </p>
      )}
      {!none && load.status === 'ready' && (
        <>
          <div className="brain-summary">
            <p className="brain-muted" aria-live="polite">
              {plural(shown.length, 'fact')}
              {shown.length < rows.length && ` of ${rows.length}`}
            </p>
            {filtering && (
              <button
                type="button"
                className="btn-secondary brain-clear"
                onClick={() => setFilters({ ...NO_FILTERS, sort: filters.sort })}
              >
                Clear filters
              </button>
            )}
          </div>
          {shown.length === 0 ? (
            <p className="empty">
              {rows.length
                ? 'Nothing matches these filters.'
                : 'Nothing saved in these spaces yet. Capture something first.'}
            </p>
          ) : (
            <ul className="brain-list">
              {shown.map((row) => (
                <FactRow
                  key={row.id}
                  row={row}
                  open={open === row.id}
                  onToggle={() =>
                    setOpen((current) => (current === row.id ? null : row.id))
                  }
                />
              ))}
            </ul>
          )}
        </>
      )}
    </main>
  )
}

/** One fact (or relation): "entity · key = value", opening into its details. */
function FactRow({
  row,
  open,
  onToggle,
}: {
  row: BrainRow
  open: boolean
  onToggle: () => void
}) {
  const panelId = `brain-${row.id.replace(/[^a-z0-9]+/gi, '-')}`
  const relation = row.kind === 'relation'
  return (
    <li className="brain-fact" data-open={open} data-replaced={row.replaced}>
      <button
        type="button"
        className="brain-row"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={onToggle}
      >
        <span className="brain-caret" aria-hidden="true" />
        <span className="brain-text">
          <span className="brain-entity-name">{row.entity}</span>
          <span className="brain-sep" aria-hidden="true">
            ·
          </span>
          <span className="mono brain-key">{row.key}</span>
          <span className="brain-sep" aria-hidden="true">
            {relation ? '→' : '='}
          </span>
          <span className="brain-value">{row.value}</span>
        </span>
        <span className="brain-tags">
          {relation && <span className="tag">relation</span>}
          {row.replaced && (
            <span className="tag" data-tone="note">
              replaced
            </span>
          )}
        </span>
        <span className="brain-date">{formatDate(row.created_at)}</span>
      </button>
      {open && (
        <dl id={panelId} className="brain-detail">
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
      )}
    </li>
  )
}
