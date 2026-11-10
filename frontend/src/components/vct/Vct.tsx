import { useEffect, useId, useState } from 'react'
import {
  activeTags,
  vctApi,
  type FactTagDetail,
  type FactTags,
  type OnboardingPreview,
  type OnboardingStatus,
  type TagAction,
  type TagKind,
  type TaggerStatus,
  type VctApi,
  type VctCoverage,
  type VctMap,
} from '@/api/vct'
import {
  NO_VCT_FILTER,
  filterFromOnboarding,
  hasVctFilter,
  useVctMap,
  type VctFilterValue,
} from '@/components/vct/vctState'
import '@/components/vct/vct.css'

/*
 * VCT tags on facts: chips, the editor, Ask's filter bar, Brain's coverage view
 * and the admin tagger panel. Facts stay in Agent Memory; tags are fact id +
 * node/goal, set every 3 hours by the tagger and fixed here by people.
 */

const percent = (weight: number) => `${(weight * 100).toFixed(1)}%`

/** A fact's node and goal as two small chips; "tagging within 3 h" before the tagger ran. */
export function VctTags({
  tags,
  tagged = true,
  business = true,
}: {
  tags: FactTags | null | undefined
  tagged?: boolean
  /** False when the tagger judged the fact not business. */
  business?: boolean
}) {
  if (!tags) {
    if (tagged && !business)
      return (
        <span
          className="tag vct-pending"
          title="The tagger found no value-chain match; add a tag if it is business"
        >
          not business
        </span>
      )
    return tagged ? null : (
      <span className="tag vct-pending" title="The VCT tagger runs every 3 hours">
        tagging within 3 h
      </span>
    )
  }
  const confirmed = (source: string) =>
    source === 'user' ? ' · confirmed by a person' : ''
  return (
    <span className="vct-tags">
      {tags.node && (
        <span
          className="tag vct-chip"
          data-kind="node"
          data-source={tags.node.source}
          title={`Node · ${tags.node.name}${tags.node.domain ? ` · ${tags.node.domain}` : ''}${confirmed(tags.node.source)}`}
        >
          <span className="mono">{tags.node.id}</span> {tags.node.name}
        </span>
      )}
      {tags.goal && (
        <span
          className="tag vct-chip"
          data-kind="goal"
          data-source={tags.goal.source}
          title={`Goal · ${tags.goal.name}${tags.goal.section ? ` · ${tags.goal.section}` : ''}${confirmed(tags.goal.source)}`}
        >
          <span className="mono">{tags.goal.id}</span> {tags.goal.name}
        </span>
      )}
    </span>
  )
}

type EditorLoad =
  | { status: 'loading' }
  | { status: 'missing' }
  | { status: 'error'; message: string }
  | { status: 'ready'; detail: FactTagDetail }

const messageOf = (error: unknown, fallback: string) =>
  error instanceof Error ? error.message : fallback

/**
 * Fix a fact's node and goal: pick one of the tagger's top 3, any node or goal
 * from the map, confirm the current one, or remove it. Saved at once, for
 * everyone who can read the fact.
 */
export function TagEditor({
  factId,
  api = vctApi,
  onChange,
}: {
  factId: string
  api?: VctApi
  onChange?: (tags: FactTags | null) => void
}) {
  const map = useVctMap(api)
  const [load, setLoad] = useState<EditorLoad>({ status: 'loading' })
  const [saving, setSaving] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    api
      .factTags(factId, controller.signal)
      .then((detail) => setLoad({ status: 'ready', detail }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        const status = (error as { status?: number }).status
        setLoad(
          status === 404
            ? { status: 'missing' }
            : { status: 'error', message: messageOf(error, 'Failed') },
        )
      })
    return () => controller.abort()
  }, [api, factId])

  const edit = (kind: TagKind, action: TagAction, tag?: string) => {
    setSaving(true)
    setFailure(null)
    api
      .editTag(factId, { kind, action, tag })
      .then((detail) => {
        setLoad({ status: 'ready', detail })
        onChange?.(activeTags(detail))
      })
      .catch((error: unknown) => setFailure(messageOf(error, 'Saving failed')))
      .finally(() => setSaving(false))
  }

  if (load.status === 'loading') return <p className="vct-muted">Loading tags…</p>
  if (load.status === 'missing')
    return (
      <p className="vct-muted">
        Not tagged yet. The VCT tagger runs every 3 hours; tags appear after its next run.
      </p>
    )
  if (load.status === 'error')
    return (
      <p className="error" role="alert">
        {load.message}
      </p>
    )

  const { detail } = load
  return (
    <div className="vct-editor">
      {!detail.business && (
        <p className="vct-muted">
          The tagger marked this fact not business. Add a node or goal if it is.
        </p>
      )}
      <KindEditor
        kind="node"
        label="Node"
        tags={detail.nodes}
        map={map}
        disabled={saving}
        onEdit={edit}
      />
      <KindEditor
        kind="goal"
        label="Goal"
        tags={detail.goals}
        map={map}
        disabled={saving}
        onEdit={edit}
      />
      {failure && (
        <p className="error" role="alert">
          {failure}
        </p>
      )}
      <p className="vct-muted">
        Changes apply for everyone who can read {detail.scope} and help the tagger learn.
      </p>
    </div>
  )
}

function KindEditor({
  kind,
  label,
  tags,
  map,
  disabled,
  onEdit,
}: {
  kind: TagKind
  label: string
  tags: FactTagDetail['nodes']
  map: VctMap | null
  disabled: boolean
  onEdit: (kind: TagKind, action: TagAction, tag?: string) => void
}) {
  const pickId = useId()
  const [current, ...alternatives] = tags
  const word = label.toLowerCase()
  return (
    <fieldset className="vct-kind" disabled={disabled}>
      <legend>{label}</legend>
      {current ? (
        <div className="vct-current">
          <span className="tag vct-chip" data-kind={kind} data-source={current.source}>
            <span className="mono">{current.id}</span> {current.name}
          </span>
          <span className="vct-muted">
            {current.source === 'user' ? 'confirmed' : 'suggested by the tagger'}
          </span>
          {current.source !== 'user' && (
            <button
              type="button"
              className="btn-secondary vct-small"
              onClick={() => onEdit(kind, 'accept')}
            >
              Confirm {word}
            </button>
          )}
          <button
            type="button"
            className="btn-secondary vct-small"
            onClick={() => onEdit(kind, 'remove')}
          >
            Remove {word}
          </button>
        </div>
      ) : (
        <p className="vct-muted">No {word}.</p>
      )}
      {alternatives.length > 0 && (
        <div className="vct-alternatives">
          <span className="vct-muted">Other matches:</span>
          {alternatives.map((alt) => (
            <button
              key={alt.id}
              type="button"
              className="ask-chip vct-alt"
              onClick={() => onEdit(kind, 'change', alt.id)}
            >
              <span className="mono">{alt.id}</span> {alt.name}
            </button>
          ))}
        </div>
      )}
      <label htmlFor={pickId} className="vct-pick-label">
        {current ? `Choose another ${word}` : `Add a ${word}`}
      </label>
      <select
        id={pickId}
        className="vct-select"
        value=""
        disabled={!map}
        onChange={(e) => {
          if (e.target.value) onEdit(kind, 'change', e.target.value)
        }}
      >
        <option value="">{map ? 'Pick from the map…' : 'Loading the map…'}</option>
        {map && <MapOptions kind={kind} map={map} />}
      </select>
    </fieldset>
  )
}

/** Every node by domain, every goal by section with its EBITDA weight, or every domain. */
export function MapOptions({ kind, map }: { kind: TagKind | 'domain'; map: VctMap }) {
  if (kind === 'domain')
    return (
      <>
        {map.domains.map((d) => (
          <option key={d.id} value={d.id}>
            {d.name}
          </option>
        ))}
      </>
    )
  if (kind === 'node')
    return (
      <>
        {map.domains.map((d) => (
          <optgroup key={d.id} label={d.name}>
            {d.nodes.map((n) => (
              <option key={n.id} value={n.id}>
                {n.id} · {n.name}
              </option>
            ))}
          </optgroup>
        ))}
      </>
    )
  return (
    <>
      {map.sections.map((s) => (
        <optgroup key={s.id} label={`${s.label} · ${percent(s.ebitda_weight)} of EBITDA`}>
          {s.goals.map((g) => (
            <option key={g.id} value={g.id}>
              {g.id} · {g.name} ({percent(g.weight)})
            </option>
          ))}
        </optgroup>
      ))}
    </>
  )
}

const FILTER_KINDS = [
  { key: 'goals', kind: 'goal', label: 'Goal' },
  { key: 'nodes', kind: 'node', label: 'Node' },
  { key: 'domains', kind: 'domain', label: 'Domain' },
] as const

/**
 * The value-driven column's filter. It starts on the user's onboarded domains
 * (`mine`); any goal, node or domain can be added or removed, and the two
 * shortcuts put the user's own domains or nodes back.
 */
export function VctFilterBar({
  value,
  onChange,
  mine = null,
  api = vctApi,
}: {
  value: VctFilterValue
  onChange: (value: VctFilterValue) => void
  /** The user's onboarding; null while loading or when they have none. */
  mine?: OnboardingStatus | null
  api?: VctApi
}) {
  const map = useVctMap(api)
  const name = (kind: TagKind | 'domain', id: string) => {
    if (!map) return id
    if (kind === 'domain') return map.domains.find((d) => d.id === id)?.name ?? id
    if (kind === 'node')
      return map.domains.flatMap((d) => d.nodes).find((n) => n.id === id)?.name ?? id
    return map.sections.flatMap((s) => s.goals).find((g) => g.id === id)?.name ?? id
  }
  const myDomains = mine?.domains ?? []
  const myNodes = mine?.nodes ?? []
  const intro =
    myDomains.length > 0
      ? 'Starts on your value chain domains. Change it to look at any part of the value chain.'
      : 'You are not mapped to the value chain yet, so pick a domain, node or goal.'
  const showShortcuts = myDomains.length > 0 || hasVctFilter(value)
  return (
    <section className="vct-filter" aria-label="Value-driven filter">
      <p className="vct-filter-intro">
        <strong>Value-driven filter</strong> <span className="ask-muted">{intro}</span>
      </p>
      {showShortcuts && (
        <div className="ask-chips vct-filter-mine">
          {myDomains.length > 0 && (
            <button
              type="button"
              className="ask-chip"
              onClick={() => onChange(filterFromOnboarding(mine))}
            >
              My domains
            </button>
          )}
          {myNodes.length > 0 && (
            <button
              type="button"
              className="ask-chip"
              onClick={() =>
                onChange({ ...NO_VCT_FILTER, nodes: myNodes.map((n) => n.id) })
              }
            >
              Only my nodes
            </button>
          )}
          {hasVctFilter(value) && (
            <button
              type="button"
              className="ask-chip"
              onClick={() => onChange(NO_VCT_FILTER)}
            >
              Clear
            </button>
          )}
        </div>
      )}
      {FILTER_KINDS.map(({ key, kind, label }) => (
        <div key={key} className="vct-filter-kind">
          <label className="vct-filter-label">
            {label}
            <select
              className="vct-select"
              value=""
              disabled={!map}
              onChange={(e) => {
                const id = e.target.value
                if (id && !value[key].includes(id))
                  onChange({ ...value, [key]: [...value[key], id] })
              }}
            >
              <option value="">
                {map ? `Add a ${label.toLowerCase()}…` : 'Loading…'}
              </option>
              {map && <MapOptions kind={kind} map={map} />}
            </select>
          </label>
          {value[key].map((id) => (
            <button
              key={id}
              type="button"
              className="ask-chip vct-on"
              aria-label={`Remove ${label.toLowerCase()} ${name(kind, id)}`}
              onClick={() =>
                onChange({ ...value, [key]: value[key].filter((v) => v !== id) })
              }
            >
              <span className="mono">{id}</span> {name(kind, id)}{' '}
              <span aria-hidden="true">×</span>
            </button>
          ))}
        </div>
      ))}
    </section>
  )
}

export interface CoverageFact {
  id: string
  entity: string
  key: string
  value: string
  tags: FactTags | null | undefined
  tagged: boolean
  /** False when the tagger judged it not business: left out of the gaps. */
  business?: boolean
}

/**
 * The map of where knowledge is: fact counts per domain and value-chain
 * section, each section with its share of EBITDA. A dashed cell has map nodes
 * but no facts, a gap. The tagged facts themselves are listed below it.
 */
export function VctCoverageView({
  facts,
  api = vctApi,
}: {
  facts: CoverageFact[]
  api?: VctApi
}) {
  const map = useVctMap(api)
  const [coverage, setCoverage] = useState<VctCoverage | null>(null)
  const [failure, setFailure] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    api
      .coverage(controller.signal)
      .then(setCoverage)
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setFailure(messageOf(error, 'Failed'))
      })
    return () => controller.abort()
  }, [api])

  const pending = facts.filter((f) => !f.tagged).length

  return (
    <section className="vct-coverage" aria-label="Value chain coverage">
      <h2 className="vct-heading">Where knowledge sits</h2>
      {failure && (
        <p className="error" role="alert">
          {failure}
        </p>
      )}
      {coverage && map && (
        <>
          <p className="vct-muted">
            {coverage.tagged_facts} tagged facts in the spaces you can read ·{' '}
            {coverage.without_goal} without a goal · {coverage.not_business} not business
            · {pending} listed here waiting for the tagger
          </p>
          <div className="vct-grid-wrap">
            <table className="vct-grid">
              <caption className="visually-hidden">Facts per domain and section</caption>
              <thead>
                <tr>
                  <th scope="col">Domain</th>
                  {map.sections.map((s) => (
                    <th
                      key={s.id}
                      scope="col"
                      title={`${percent(s.ebitda_weight)} of EBITDA`}
                    >
                      {s.label}
                      <span className="vct-share">
                        {percent(s.ebitda_weight)} of EBITDA
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {map.domains.map((d) => (
                  <tr key={d.id}>
                    <th scope="row">{d.name}</th>
                    {map.sections.map((s) => {
                      const cell = coverage.cells.find(
                        (c) => c.domain_id === d.id && c.section_id === s.id,
                      )
                      if (!cell)
                        return (
                          <td key={s.id} className="vct-none">
                            –
                          </td>
                        )
                      const level =
                        cell.facts >= 10 ? 'high' : cell.facts > 0 ? 'some' : undefined
                      return (
                        <td
                          key={s.id}
                          data-gap={cell.facts === 0 ? '' : undefined}
                          data-level={level}
                          title={`${cell.nodes} node${cell.nodes === 1 ? '' : 's'}, ${cell.facts} fact${cell.facts === 1 ? '' : 's'}`}
                        >
                          {cell.facts}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="vct-muted">
            Dashed cells have nodes but no facts yet: a gap. “–” means no node sits there.
          </p>
        </>
      )}
    </section>
  )
}

const TIME = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})
const when = (iso: string | null) => (iso ? TIME.format(new Date(iso)) : '—')

/** Admin: what the tagger tags, its last run, how often people corrected it, and Run now. */
export function TaggerPanel({ api = vctApi }: { api?: VctApi }) {
  const [status, setStatus] = useState<TaggerStatus | null>(null)
  const [failure, setFailure] = useState<string | null>(null)
  const running = status?.running ?? false

  useEffect(() => {
    const controller = new AbortController()
    const read = () => {
      api
        .tagger(controller.signal)
        .then((s) => {
          setStatus(s)
          setFailure(null)
        })
        .catch((error: unknown) => {
          if (!controller.signal.aborted) setFailure(messageOf(error, 'Failed'))
        })
    }
    read()
    // While a run is going, check back every few seconds.
    const timer = running ? window.setInterval(read, 4000) : undefined
    return () => {
      controller.abort()
      window.clearInterval(timer)
    }
  }, [api, running])

  const run = (retag = false) => {
    setFailure(null)
    api
      .runTagger(retag)
      .then(setStatus)
      .catch((error: unknown) => setFailure(messageOf(error, 'Failed')))
  }

  const last = status?.current ?? status?.last
  const stats = status?.stats
  return (
    <section className="panel vct-tagger" aria-labelledby="vct-tagger-heading">
      <div className="vct-tagger-head">
        <h2 id="vct-tagger-heading">VCT tagger</h2>
        <div className="vct-current">
          <button
            type="button"
            className="btn-secondary"
            disabled={!status || running}
            title="Tag every fact in the tagged spaces again; tags people set stay"
            onClick={() => run(true)}
          >
            Re-tag all
          </button>
          <button
            type="button"
            className="btn"
            disabled={!status || running}
            onClick={() => run()}
          >
            {running ? 'Running…' : 'Run now'}
          </button>
        </div>
      </div>
      {failure && (
        <p className="error" role="alert">
          {failure}
        </p>
      )}
      {status && (
        <>
          <p className="vct-muted">
            Tags facts with their top 3 nodes and goals every {status.interval_hours} h
            {status.enabled ? '' : ' (scheduled runs are off)'}, version {status.version}.
            Tagged spaces:{' '}
            <span className="mono">{status.scopes.join(', ') || 'none'}</span>
          </p>
          <dl className="vct-stats">
            <div>
              <dt>Last run</dt>
              <dd>{last ? when(last.started_at) : 'not yet'}</dd>
            </div>
            <div>
              <dt>Next run</dt>
              <dd>{when(status.next_run_at)}</dd>
            </div>
            <div>
              <dt>Tagged facts</dt>
              <dd>{status.tagged_facts}</dd>
            </div>
            <div>
              <dt>Not business</dt>
              <dd>{status.not_business}</dd>
            </div>
            <div>
              <dt>Corrected ({stats?.days ?? 7} days)</dt>
              <dd>
                {stats?.correction_rate == null
                  ? '—'
                  : `${Math.round(stats.correction_rate * 100)}% of ${stats.edits}`}
              </dd>
            </div>
          </dl>
          {last && (
            <p className="mono vct-muted">
              {running ? 'running: ' : 'last run: '}
              {last.listed} seen · {last.new} new · {last.tagged} tagged ·{' '}
              {last.not_business} not business · {last.failed} failed
              {last.carried ? ` · ${last.carried} carried` : ''}
              {last.capped ? ' · capped, the rest next run' : ''}
              {last.error ? ` · ${last.error}` : ''}
            </p>
          )}
          {stats && stats.confusions.length > 0 && (
            <div className="vct-alternatives">
              <span className="vct-muted">Most corrected:</span>
              {stats.confusions.map((c) => (
                <span key={`${c.old}-${c.new}`} className="tag mono">
                  {c.old} → {c.new ?? 'removed'} · {c.times}
                </span>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  )
}

type OnboardStep =
  | { step: 'idle' }
  | { step: 'busy' }
  | { step: 'error'; message: string }
  | { step: 'preview'; preview: OnboardingPreview }
  | { step: 'saved'; status: OnboardingStatus }

/**
 * Admin: onboard or re-onboard someone to the value chain. Describe their work,
 * see which VCT nodes recall matches, tick up to 8 and save them for that
 * user (marked "confirmed by admin"). Their domains follow from the nodes.
 */
export function OnboardUser({ api = vctApi }: { api?: VctApi }) {
  const emailId = useId()
  const workId = useId()
  const [email, setEmail] = useState('')
  const [work, setWork] = useState('')
  const [chosen, setChosen] = useState<string[]>([])
  const [state, setState] = useState<OnboardStep>({ step: 'idle' })
  const [current, setCurrent] = useState<OnboardingStatus | null>(null)

  const lookUp = () => {
    const who = email.trim().toLowerCase()
    if (!who) return
    api
      .userOnboarding(who)
      .then((status) => {
        setCurrent(status)
        if (status.primary_work && !work) setWork(status.primary_work)
      })
      .catch(() => setCurrent(null))
  }

  const preview = () => {
    setState({ step: 'busy' })
    api
      .previewOnboarding(work.trim())
      .then((p) => {
        setChosen(p.suggested.slice(0, 8))
        setState({ step: 'preview', preview: p })
      })
      .catch((error: unknown) =>
        setState({ step: 'error', message: messageOf(error, 'Matching failed') }),
      )
  }

  const save = () => {
    setState({ step: 'busy' })
    api
      .setUserNodes(email.trim().toLowerCase(), chosen)
      .then((status) => {
        setCurrent(status)
        setState({ step: 'saved', status })
      })
      .catch((error: unknown) =>
        setState({ step: 'error', message: messageOf(error, 'Saving failed') }),
      )
  }

  const toggle = (id: string) =>
    setChosen((c) =>
      c.includes(id) ? c.filter((x) => x !== id) : c.length < 8 ? [...c, id] : c,
    )

  const busy = state.step === 'busy'
  return (
    <section className="panel vct-tagger" aria-labelledby="vct-onboard-heading">
      <h2 id="vct-onboard-heading" className="vct-heading">
        Onboard a user to the value chain
      </h2>
      <p className="vct-muted">
        Describe what the person does. Recall suggests VCT nodes; tick the right ones (up
        to 8, the first is primary) and save. Re-onboarding replaces their nodes.
      </p>
      <label htmlFor={emailId} className="vct-pick-label">
        Email
      </label>
      <input
        id={emailId}
        type="email"
        className="vct-select"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        onBlur={lookUp}
        placeholder="name@spreetail.com"
      />
      {current?.onboarded && (
        <p className="vct-muted">
          Now mapped to{' '}
          {current.nodes.map((n) => `${n.id} ${n.name}`).join(', ') || 'no nodes'}
          {current.domains.length
            ? ` · ${current.domains.map((d) => d.name).join(', ')}`
            : ''}
        </p>
      )}
      <label htmlFor={workId} className="vct-pick-label">
        How their day looks
      </label>
      <textarea
        id={workId}
        className="vct-select vct-textarea"
        rows={3}
        value={work}
        onChange={(e) => setWork(e.target.value)}
        placeholder="I receive trucks at the Dallas warehouse and pick carriers for outbound orders."
      />
      <div className="vct-current">
        <button
          type="button"
          className="btn-secondary"
          disabled={busy || work.trim().length < 3}
          onClick={preview}
        >
          Suggest nodes
        </button>
        {state.step === 'preview' && (
          <button
            type="button"
            className="btn"
            disabled={busy || !email.trim() || chosen.length === 0}
            onClick={save}
          >
            Save {chosen.length} node{chosen.length === 1 ? '' : 's'}
          </button>
        )}
      </div>
      {state.step === 'error' && (
        <p className="error" role="alert">
          {state.message}
        </p>
      )}
      {state.step === 'saved' && (
        <output className="vct-muted">
          Saved for {state.status.email}:{' '}
          {state.status.domains.map((d) => d.name).join(', ') || 'no domains'}.
        </output>
      )}
      {state.step === 'preview' && (
        <ul className="vct-gap-list">
          {state.preview.clauses.map((c) => (
            <li key={c.clause}>
              <p className="vct-muted">“{c.clause}”</p>
              <div className="vct-alternatives">
                {c.candidates.map((n) => (
                  <label key={n.id} className="vct-compare">
                    <input
                      type="checkbox"
                      checked={chosen.includes(n.id)}
                      onChange={() => toggle(n.id)}
                    />
                    <span className="mono">{n.id}</span> {n.name}
                  </label>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
