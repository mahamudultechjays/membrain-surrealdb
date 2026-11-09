import { useEffect, useState } from 'react'
import {
  activeTags,
  vctApi,
  type FactTagDetail,
  type FactTags,
  type TagKind,
  type TagRef,
  type VctApi,
  type VctMap,
} from '@/api/vct'
import { MapOptions } from '@/components/vct/Vct'
import { inReview, timeLeft, useVctMap } from '@/components/vct/vctState'
import '@/components/vct/vct.css'

/*
 * Brain › Review: tags the tagger added in the last 2 days, for people to
 * confirm, change, or mark not business. Untouched tags stay as the tagger set
 * them. Facts are grouped by domain (or node); not-business facts sit in their
 * own tab with the tagger's best guesses ready for "Tag it".
 */

export interface ReviewFact {
  id: string
  entity: string
  key: string
  value: string
  space: string
  tags: FactTags | null | undefined
  business: boolean
  taggedAt: string | null
  reviewedAt: string | null
}

const PAGE = 4
type GroupBy = 'domain' | 'node'
type Tab = 'tags' | 'off'

const messageOf = (error: unknown) => (error instanceof Error ? error.message : 'Failed')

/** The banner across Brain while there is something to review. */
export function ReviewBanner({ count }: { count: number }) {
  if (count === 0) return null
  return (
    <p className="vct-banner">
      <strong>
        {count} new tag{count === 1 ? '' : 's'} to review
      </strong>
      <span>
        {' '}
        · from tagger runs in the last 2 days; untouched tags stay as the tagger set them
      </span>
      <a href="#/brain/review">Review now</a>
    </p>
  )
}

interface Group {
  key: string
  name: string
  facts: ReviewFact[]
  sections: string
  nodes: { id: string; name: string; count: number }[]
}

function groupFacts(facts: ReviewFact[], by: GroupBy, map: VctMap | null): Group[] {
  const allNodes = map?.domains.flatMap((d) => d.nodes) ?? []
  const groups = new Map<string, Group>()
  for (const fact of facts) {
    const node = fact.tags?.node
    const key = !node ? 'none' : by === 'domain' ? (node.domain_id ?? 'none') : node.id
    const name = !node
      ? 'No node'
      : by === 'domain'
        ? (map?.domains.find((d) => d.id === node.domain_id)?.name ?? node.domain ?? key)
        : `${node.id} ${node.name}`
    const group = groups.get(key) ?? { key, name, facts: [], sections: '', nodes: [] }
    group.facts.push(fact)
    groups.set(key, group)
  }
  for (const group of groups.values()) {
    const sections = new Map<string, number>()
    const nodes = new Map<string, number>()
    for (const fact of group.facts) {
      const node = fact.tags?.node
      if (!node) continue
      const sectionId =
        allNodes.find((n) => n.id === node.id)?.section_id ?? node.section_id
      const label = map?.sections.find((s) => s.id === sectionId)?.label ?? sectionId
      sections.set(label, (sections.get(label) ?? 0) + 1)
      nodes.set(node.id, (nodes.get(node.id) ?? 0) + 1)
    }
    group.sections = [...sections]
      .sort((a, b) => b[1] - a[1])
      .map(([label, n]) => `${label} (${n})`)
      .join(', ')
    group.nodes = [...nodes]
      .sort((a, b) => b[1] - a[1])
      .map(([id, count]) => ({
        id,
        name: allNodes.find((n) => n.id === id)?.name ?? id,
        count,
      }))
  }
  return [...groups.values()].sort((a, b) => b.facts.length - a.facts.length)
}

/** The Review view: tabs, grouping, rows and the not-business list. */
export function ReviewView({
  facts,
  api = vctApi,
}: {
  facts: ReviewFact[]
  api?: VctApi
}) {
  const map = useVctMap(api)
  const [tab, setTab] = useState<Tab>('tags')
  const [groupBy, setGroupBy] = useState<GroupBy>('domain')
  const [done, setDone] = useState<Set<string>>(new Set())
  const [changed, setChanged] = useState<Record<string, FactTags | null>>({})
  const [shown, setShown] = useState<Record<string, number>>({})
  const [folded, setFolded] = useState<Set<string>>(new Set())
  const [failure, setFailure] = useState<string | null>(null)

  const pending = inReview(facts)
    .filter((f) => !done.has(f.id))
    .map((f) => (f.id in changed ? { ...f, tags: changed[f.id] } : f))
  const tagged = pending.filter((f) => f.business)
  const offTopic = pending.filter((f) => !f.business)
  const finish = (ids: string[]) => setDone((d) => new Set([...d, ...ids]))
  const act = (
    fact: ReviewFact,
    action: 'confirm' | 'not_business' | 'keep' | 'tag_guesses',
  ) => {
    setFailure(null)
    api
      .editTag(fact.id, { action })
      .then(() => finish([fact.id]))
      .catch((error: unknown) => setFailure(messageOf(error)))
  }
  const confirmAll = (group: Group) => {
    setFailure(null)
    api
      .reviewFacts(
        group.facts.map((f) => f.id),
        'confirm',
      )
      .then((result) => finish(result.done))
      .catch((error: unknown) => setFailure(messageOf(error)))
  }
  const toggle = (key: string) =>
    setFolded((f) => {
      const next = new Set(f)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  const groups = groupFacts(tagged, groupBy, map)
  return (
    <section className="vct-review" aria-label="Review new tags">
      <div className="vct-review-bar">
        <div className="vct-tabs">
          <button
            type="button"
            aria-pressed={tab === 'tags'}
            className="vct-tab"
            onClick={() => setTab('tags')}
          >
            New tags · {tagged.length}
          </button>
          <button
            type="button"
            aria-pressed={tab === 'off'}
            className="vct-tab"
            onClick={() => setTab('off')}
          >
            Marked not business · {offTopic.length}
          </button>
        </div>
        {tab === 'tags' && (
          <div className="vct-groupby">
            <span className="vct-muted">Group by</span>
            {(['domain', 'node'] as const).map((by) => (
              <button
                key={by}
                type="button"
                aria-pressed={groupBy === by}
                className="vct-seg"
                onClick={() => setGroupBy(by)}
              >
                {by === 'domain' ? 'Domain' : 'Node'}
              </button>
            ))}
          </div>
        )}
      </div>
      {failure && (
        <p className="error" role="alert">
          {failure}
        </p>
      )}

      {tab === 'tags' &&
        (groups.length === 0 ? (
          <p className="vct-muted">
            Nothing new to review. Tags from the next run appear here.
          </p>
        ) : (
          groups.map((group) => {
            const open = !folded.has(group.key)
            const limit = shown[group.key] ?? PAGE
            return (
              <section key={group.key} className="vct-group" aria-label={group.name}>
                <header className="vct-group-head">
                  <button
                    type="button"
                    className="vct-fold"
                    aria-expanded={open}
                    onClick={() => toggle(group.key)}
                  >
                    {group.name}
                  </button>
                  <span className="vct-muted">
                    {group.facts.length} fact{group.facts.length === 1 ? '' : 's'}
                    {group.sections && ` · mostly ${group.sections}`}
                  </span>
                  {groupBy === 'domain' && (
                    <span className="vct-tags">
                      {group.nodes.slice(0, 4).map((n) => (
                        <span key={n.id} className="tag vct-chip" data-kind="node">
                          <span className="mono">{n.id}</span> {n.name} · {n.count}
                        </span>
                      ))}
                    </span>
                  )}
                  <button
                    type="button"
                    className="btn vct-small vct-push"
                    onClick={() => confirmAll(group)}
                  >
                    Confirm all {group.facts.length}
                  </button>
                </header>
                {open && (
                  <>
                    <div className="vct-row vct-row-head" aria-hidden="true">
                      <span>Fact</span>
                      <span>Node</span>
                      <span>Goal</span>
                      <span>Review</span>
                    </div>
                    {group.facts.slice(0, limit).map((fact) => (
                      <ReviewRow
                        key={fact.id}
                        fact={fact}
                        api={api}
                        map={map}
                        onChanged={(tags) =>
                          setChanged((c) => ({ ...c, [fact.id]: tags }))
                        }
                        onConfirm={() => act(fact, 'confirm')}
                        onNotBusiness={() => act(fact, 'not_business')}
                      />
                    ))}
                    {group.facts.length > limit && (
                      <div className="vct-more">
                        <span className="vct-muted">
                          Showing {limit} of {group.facts.length}
                        </span>
                        <button
                          type="button"
                          className="btn-secondary vct-small"
                          onClick={() =>
                            setShown((s) => ({ ...s, [group.key]: limit + PAGE }))
                          }
                        >
                          Show {Math.min(PAGE, group.facts.length - limit)} more
                        </button>
                      </div>
                    )}
                  </>
                )}
              </section>
            )
          })
        ))}

      {tab === 'off' &&
        (offTopic.length === 0 ? (
          <p className="vct-muted">No new facts were marked not business.</p>
        ) : (
          <section className="vct-group vct-off" aria-label="Marked not business">
            <header className="vct-group-head">
              <strong>Marked not business · {offTopic.length}</strong>
              <span className="vct-muted">
                Tag any that are business; the best guess is ready
              </span>
            </header>
            {offTopic.map((fact) => (
              <GuessRow
                key={fact.id}
                fact={fact}
                api={api}
                map={map}
                onTag={() => act(fact, 'tag_guesses')}
                onKeep={() => act(fact, 'keep')}
                onPicked={() => finish([fact.id])}
              />
            ))}
          </section>
        ))}
    </section>
  )
}

function FactCell({ fact }: { fact: ReviewFact }) {
  return (
    <span className="vct-fact">
      <span>
        <strong>{fact.entity}</strong> · <span className="mono">{fact.key}</span> ={' '}
        {fact.value}
      </span>
      <span className="vct-muted">
        {fact.space.split('/').pop()}
        {fact.taggedAt && ` · ${timeLeft(fact.taggedAt)} left`}
      </span>
    </span>
  )
}

function ReviewRow({
  fact,
  api,
  map,
  onChanged,
  onConfirm,
  onNotBusiness,
}: {
  fact: ReviewFact
  api: VctApi
  map: VctMap | null
  onChanged: (tags: FactTags | null) => void
  onConfirm: () => void
  onNotBusiness: () => void
}) {
  const [picking, setPicking] = useState<TagKind | null>(null)
  const chip = (kind: TagKind, tag: TagRef | null | undefined) => (
    <button
      type="button"
      className="tag vct-chip vct-chip-button"
      data-kind={kind}
      aria-expanded={picking === kind}
      aria-label={`Change ${kind}: ${tag ? `${tag.id} ${tag.name}` : 'none'}`}
      onClick={() => setPicking(picking === kind ? null : kind)}
    >
      {tag ? (
        <>
          <span className="mono">{tag.id}</span> {tag.name}
        </>
      ) : (
        `+ ${kind}`
      )}{' '}
      {picking === kind ? '▴' : '▾'}
    </button>
  )
  return (
    <div className="vct-row-wrap" data-open={picking ? '' : undefined}>
      <div className="vct-row">
        <FactCell fact={fact} />
        {chip('node', fact.tags?.node)}
        {chip('goal', fact.tags?.goal)}
        <span className="vct-actions">
          <button
            type="button"
            className="btn-secondary vct-small vct-confirm"
            onClick={onConfirm}
          >
            Confirm
          </button>
          <button
            type="button"
            className="btn-secondary vct-small"
            onClick={onNotBusiness}
          >
            Not business
          </button>
        </span>
      </div>
      {picking && (
        <ChipPicker
          factId={fact.id}
          kind={picking}
          api={api}
          map={map}
          onPicked={(detail) => {
            onChanged(activeTags(detail))
            setPicking(null)
          }}
        />
      )}
    </div>
  )
}

/** Under a row: the other top matches in one click, or any node or goal from the map. */
function ChipPicker({
  factId,
  kind,
  api,
  map,
  onPicked,
}: {
  factId: string
  kind: TagKind
  api: VctApi
  map: VctMap | null
  onPicked: (detail: FactTagDetail) => void
}) {
  const [detail, setDetail] = useState<FactTagDetail | null>(null)
  const [failure, setFailure] = useState<string | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    api
      .factTags(factId, controller.signal)
      .then(setDetail)
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setFailure(messageOf(error))
      })
    return () => controller.abort()
  }, [api, factId])

  const pick = (tag: string) => {
    setFailure(null)
    api
      .editTag(factId, { kind, action: 'change', tag })
      .then(onPicked)
      .catch((error: unknown) => setFailure(messageOf(error)))
  }
  const options = detail
    ? kind === 'node'
      ? [...detail.nodes, ...detail.guess_nodes]
      : [...detail.goals, ...detail.guess_goals]
    : []
  const domainName = (id: string | null | undefined) =>
    map?.domains.find((d) => d.id === id)?.name ?? ''
  return (
    <div className="vct-picker">
      <span className="vct-muted">Change {kind} for this fact:</span>
      <div className="vct-alternatives">
        {options.map((option, i) => (
          <button
            key={option.id}
            type="button"
            className="ask-chip vct-alt"
            aria-pressed={i === 0}
            onClick={() => pick(option.id)}
          >
            <span className="mono">{option.id}</span> {option.name}
            {i === 0 ? ' (current)' : ''}
            {kind === 'node' && option.domain_id
              ? ` · ${domainName(option.domain_id)}`
              : ''}
          </button>
        ))}
        <label className="vct-filter-label vct-inline">
          or any {kind}
          <select
            className="vct-select"
            value=""
            disabled={!map}
            onChange={(e) => {
              if (e.target.value) pick(e.target.value)
            }}
          >
            <option value="">{map ? 'Pick from the map…' : 'Loading…'}</option>
            {map && <MapOptions kind={kind} map={map} />}
          </select>
        </label>
      </div>
      {failure && (
        <p className="error" role="alert">
          {failure}
        </p>
      )}
      <span className="vct-muted">
        Picking one saves it at once; a new node in another domain moves the fact to that
        group.
      </span>
    </div>
  )
}

function GuessRow({
  fact,
  api,
  map,
  onTag,
  onKeep,
  onPicked,
}: {
  fact: ReviewFact
  api: VctApi
  map: VctMap | null
  onTag: () => void
  onKeep: () => void
  onPicked: () => void
}) {
  const [detail, setDetail] = useState<FactTagDetail | null>(null)
  const [picking, setPicking] = useState<TagKind | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    api
      .factTags(fact.id, controller.signal)
      .then(setDetail)
      .catch(() => undefined)
    return () => controller.abort()
  }, [api, fact.id])
  const guess = (kind: TagKind, ref: TagRef | undefined) => (
    <button
      type="button"
      className="tag vct-chip vct-chip-button vct-guess"
      aria-expanded={picking === kind}
      aria-label={`Choose ${kind}${ref ? `, best guess ${ref.id} ${ref.name}` : ''}`}
      onClick={() => setPicking(picking === kind ? null : kind)}
    >
      {ref ? `guess ${ref.id} ${ref.name}` : `+ ${kind}`} {picking === kind ? '▴' : '▾'}
    </button>
  )
  const hasGuess = Boolean(detail?.guess_nodes.length || detail?.guess_goals.length)
  return (
    <div className="vct-row-wrap">
      <div className="vct-row">
        <FactCell fact={fact} />
        {guess('node', detail?.guess_nodes[0])}
        {guess('goal', detail?.guess_goals[0])}
        <span className="vct-actions">
          <button
            type="button"
            className="btn-secondary vct-small vct-confirm"
            disabled={!hasGuess}
            onClick={onTag}
          >
            Tag it
          </button>
          <button type="button" className="btn-secondary vct-small" onClick={onKeep}>
            Keep
          </button>
        </span>
      </div>
      {picking && (
        <ChipPicker
          factId={fact.id}
          kind={picking}
          api={api}
          map={map}
          onPicked={() => {
            setPicking(null)
            onPicked()
          }}
        />
      )}
    </div>
  )
}
