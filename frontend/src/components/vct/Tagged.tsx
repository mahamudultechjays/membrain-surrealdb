import { useState } from 'react'
import { vctApi, type FactTags, type VctApi, type VctMap } from '@/api/vct'
import { TagEditor, VctTags } from '@/components/vct/Vct'
import { useVctMap } from '@/components/vct/vctState'
import '@/components/vct/vct.css'

/*
 * Brain › Value chain: what the tagger tagged, view only. Tags are final when
 * the tagger saves them; nobody has to confirm anything. A pencil on a row
 * opens the editor for when someone wants to fix a tag.
 */

export interface TaggedFact {
  id: string
  entity: string
  key: string
  value: string
  space: string
  tags: FactTags | null | undefined
  /** False until the tagger has handled the fact. */
  tagged: boolean
  /** False when the tagger judged it not business. */
  business: boolean
  /** When the tagger tagged it, else when the fact was saved: for "newest first". */
  at: string | null
}

const PAGE = 5
const OFF_PAGE = 20
type GroupBy = 'domain' | 'node'
type Tab = 'tagged' | 'no-goal' | 'off'

interface Group {
  key: string
  name: string
  facts: TaggedFact[]
}

const time = (f: TaggedFact) => (f.at ? Date.parse(f.at) || 0 : 0)
const newestFirst = (a: TaggedFact, b: TaggedFact) => time(b) - time(a)
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

function groupFacts(facts: TaggedFact[], by: GroupBy, map: VctMap | null): Group[] {
  const groups = new Map<string, Group>()
  for (const fact of facts) {
    const node = fact.tags?.node
    const key = !node ? 'none' : by === 'domain' ? (node.domain_id ?? 'none') : node.id
    const name = !node
      ? 'No node'
      : by === 'domain'
        ? (map?.domains.find((d) => d.id === node.domain_id)?.name ?? node.domain ?? key)
        : `${node.id} ${node.name}`
    const group = groups.get(key) ?? { key, name, facts: [] }
    group.facts.push(fact)
    groups.set(key, group)
  }
  for (const group of groups.values()) group.facts.sort(newestFirst)
  return [...groups.values()].sort((a, b) => b.facts.length - a.facts.length)
}

/** Every tagged fact, grouped by domain or node, newest first, with a pencil to edit. */
export function TaggedFactsView({
  facts,
  api = vctApi,
}: {
  facts: TaggedFact[]
  api?: VctApi
}) {
  const map = useVctMap(api)
  const [tab, setTab] = useState<Tab>('tagged')
  const [groupBy, setGroupBy] = useState<GroupBy>('domain')
  // Tags edited here, so a row moves to its new group without a reload.
  const [changed, setChanged] = useState<Record<string, FactTags | null>>({})
  const [shown, setShown] = useState<Record<string, number>>({})
  const [folded, setFolded] = useState<Set<string>>(new Set())

  const current = facts
    .filter((f) => f.tagged)
    .map((f) => {
      if (!(f.id in changed)) return f
      const tags = changed[f.id]
      return { ...f, tags, business: Boolean(tags) }
    })
  const tagged = current.filter((f) => f.business && f.tags)
  const noGoal = tagged.filter((f) => !f.tags?.goal)
  const offTopic = current.filter((f) => !f.business || !f.tags).sort(newestFirst)
  const groups = groupFacts(tab === 'no-goal' ? noGoal : tagged, groupBy, map)
  const edited = (id: string) => (tags: FactTags | null) =>
    setChanged((c) => ({ ...c, [id]: tags }))
  const toggle = (key: string) =>
    setFolded((f) => {
      const next = new Set(f)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  const tabs: { id: Tab; label: string; count: number }[] = [
    { id: 'tagged', label: 'Tagged', count: tagged.length },
    { id: 'no-goal', label: 'Without a goal', count: noGoal.length },
    { id: 'off', label: 'Not business', count: offTopic.length },
  ]
  const offLimit = shown.off ?? OFF_PAGE

  return (
    <section className="vct-review" aria-label="Tagged facts">
      <h2 className="vct-heading">Tagged facts</h2>
      <div className="vct-review-bar">
        <div className="vct-tabs">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              aria-pressed={tab === t.id}
              className="vct-tab"
              onClick={() => setTab(t.id)}
            >
              {t.label} · {t.count}
            </button>
          ))}
        </div>
        {tab !== 'off' && (
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

      {tab !== 'off' &&
        (groups.length === 0 ? (
          <p className="vct-muted">
            {tab === 'tagged'
              ? 'No tagged facts in these spaces yet. The tagger runs every 3 hours.'
              : 'Every tagged fact has a goal.'}
          </p>
        ) : (
          groups.map((group) => {
            const open = !folded.has(group.key)
            const limit = shown[group.key] ?? PAGE
            const share = tagged.length
              ? Math.round((group.facts.length / tagged.length) * 100)
              : 0
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
                    {plural(group.facts.length, 'fact')}
                    {tab === 'tagged' && ` · ${share}% of tagged facts`}
                  </span>
                </header>
                {open && (
                  <>
                    {group.facts.slice(0, limit).map((fact) => (
                      <TaggedRow
                        key={fact.id}
                        fact={fact}
                        api={api}
                        onChanged={edited(fact.id)}
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
                            setShown((s) => ({ ...s, [group.key]: limit + OFF_PAGE }))
                          }
                        >
                          Show more
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
          <p className="vct-muted">The tagger marked nothing as not business.</p>
        ) : (
          <section className="vct-group vct-off" aria-label="Not business">
            <header className="vct-group-head">
              <strong>Not business · {offTopic.length}</strong>
              <span className="vct-muted">
                No value chain match. Use the pencil to tag any that are business.
              </span>
            </header>
            {offTopic.slice(0, offLimit).map((fact) => (
              <TaggedRow
                key={fact.id}
                fact={fact}
                api={api}
                onChanged={edited(fact.id)}
              />
            ))}
            {offTopic.length > offLimit && (
              <div className="vct-more">
                <span className="vct-muted">
                  Showing {offLimit} of {offTopic.length}
                </span>
                <button
                  type="button"
                  className="btn-secondary vct-small"
                  onClick={() => setShown((s) => ({ ...s, off: offLimit + OFF_PAGE }))}
                >
                  Show more
                </button>
              </div>
            )}
          </section>
        ))}
    </section>
  )
}

const DAY = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' })

function TaggedRow({
  fact,
  api,
  onChanged,
}: {
  fact: TaggedFact
  api: VctApi
  onChanged: (tags: FactTags | null) => void
}) {
  const [editing, setEditing] = useState(false)
  const when = fact.at && Date.parse(fact.at) ? DAY.format(new Date(fact.at)) : null
  return (
    <div className="vct-row-wrap" data-open={editing ? '' : undefined}>
      <div className="vct-row vct-row-tagged">
        <span className="vct-fact">
          <span>
            <strong>{fact.entity}</strong> · <span className="mono">{fact.key}</span> ={' '}
            {fact.value}
          </span>
          <span className="vct-muted">
            {fact.space.split('/').pop()}
            {when && ` · ${when}`}
          </span>
        </span>
        <VctTags tags={fact.tags} business={fact.business} />
        <button
          type="button"
          className="vct-pencil"
          aria-expanded={editing}
          aria-label={`Edit tags for ${fact.entity} · ${fact.key}`}
          title="Edit tags"
          onClick={() => setEditing((e) => !e)}
        >
          <PencilIcon />
        </button>
      </div>
      {editing && (
        <div className="vct-picker">
          <TagEditor factId={fact.id} api={api} onChange={onChanged} />
        </div>
      )}
    </div>
  )
}

function PencilIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <path
        d="M11.3 2.3a1.4 1.4 0 0 1 2 2L5.6 12 2.5 13.5 4 10.4z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
    </svg>
  )
}
