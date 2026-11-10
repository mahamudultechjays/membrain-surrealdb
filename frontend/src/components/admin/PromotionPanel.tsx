import { useCallback, useEffect, useState } from 'react'

import {
  promotionApi,
  type Evidence,
  type Group,
  type PromotionApi,
  type PromotionStatus,
  type ReviewItem,
  type RuleEdit,
  type ValueChip,
} from '@/api/promotion'
import { messageOf, statusOf } from '@/components/capture/format'
import './promotion.css'

type Filter = 'candidates' | 'flags' | 'decided' | 'groups'
const DECIDED = new Set(['active', 'rejected', 'closed', 'kept'])
const DECISION_LABELS: Record<string, string> = {
  active: 'Approved',
  rejected: 'Rejected',
  closed: 'Closed',
  kept: 'Kept',
}

const num = (n: number): string =>
  Number.isInteger(n) ? String(n) : String(+n.toFixed(2))
const day = (iso: string): string =>
  new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
const time = (iso: string | null): string =>
  iso
    ? new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
    : '—'
const title = (i: { label: string; value: string }) => `${i.label} = ${i.value}`
/** "member.a@spreetail.com" -> "Member A". */
const person = (email: string): string =>
  (email.split('@')[0] ?? email)
    .split(/[._-]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
const SOURCES: Record<string, string> = { app: 'capture', chat: 'chat' }

/**
 * Admin › Promotion (spec section 7): facts several people hold, waiting for a
 * team admin. Flags on team rules list under Flags, and in the side column
 * while another filter is on. Approve writes one team rule (wording, entity and key can be
 * edited first); Close writes a closing value over a rule.
 */
export default function PromotionPanel({ api = promotionApi }: { api?: PromotionApi }) {
  const [status, setStatus] = useState<PromotionStatus | null>(null)
  const [failure, setFailure] = useState<string | null>(null)
  const [filter, setFilter] = useState<Filter>('candidates')
  // Candidate id -> open; unset ones follow the default (only the top one open).
  const [toggled, setToggled] = useState<ReadonlyMap<number, boolean>>(new Map())
  const running = status?.running ?? false

  const read = useCallback(
    (signal?: AbortSignal) =>
      api
        .status(signal)
        .then((s) => {
          setStatus(s)
          setFailure(null)
        })
        .catch((error: unknown) => {
          if (!signal?.aborted) setFailure(messageOf(error))
        }),
    [api],
  )

  useEffect(() => {
    const controller = new AbortController()
    void read(controller.signal)
    const timer = running
      ? window.setInterval(() => void read(controller.signal), 4000)
      : undefined
    return () => {
      controller.abort()
      window.clearInterval(timer)
    }
  }, [read, running])

  const act = (call: Promise<PromotionStatus>) => {
    setFailure(null)
    call.then(setStatus).catch((error: unknown) => setFailure(messageOf(error)))
  }

  const runNow = () => {
    setFailure(null)
    api
      .run()
      .then(() => read())
      .catch((error: unknown) =>
        setFailure(
          statusOf(error) === 409 ? 'Promotion is already running.' : messageOf(error),
        ),
      )
  }

  const items = status?.items ?? []
  const candidates = items
    .filter((i) => i.kind === 'candidate' && i.status === 'open')
    .sort((a, b) => b.team_score - a.team_score)
  const flags = items.filter(
    (i) => i.kind === 'flag' && (i.status === 'open' || i.status === 'kept'),
  )
  const decided = items.filter((i) => DECIDED.has(i.status))
  const groups = status?.groups ?? []
  const isOpen = (id: number) => toggled.get(id) ?? id === candidates[0]?.id
  const toggle = (id: number) => setToggled((was) => new Map(was).set(id, !isOpen(id)))
  const rules = new Map(items.map((i) => [i.id, i]))
  const last = status?.last_run

  const counts: [Filter, string, number][] = [
    ['candidates', 'Candidates', candidates.length],
    ['flags', 'Flags', flags.length],
    ['decided', 'Decided', decided.length],
    ['groups', 'All groups', groups.length],
  ]

  return (
    <section className="promotion" aria-label="Promotion">
      <div className="promo-bar">
        <span>
          Team scope <code>{status?.team_scope ?? '…'}</code>
        </span>
        <span>
          Last run <b>{time(last?.finished_at ?? null)}</b>
          {last ? ` · ${last.new} new statements, ${last.grouped} grouped` : ''}
        </span>
        <span>
          Next run <b>{status?.enabled ? time(status.next_run_at) : 'manual only'}</b>
        </span>
        <button
          type="button"
          className="btn-secondary promo-run"
          disabled={!status || running}
          onClick={runNow}
        >
          {running ? 'Running…' : 'Run now'}
        </button>
      </div>
      {last?.error && <p className="promo-warn">Last run stopped: {last.error}</p>}
      {status && !status.model_configured && (
        <p className="promo-warn">
          ANTHROPIC_API_KEY is not set: new facts are not grouped.
        </p>
      )}
      {failure && (
        <p className="promo-error" role="alert">
          {failure}
        </p>
      )}

      <fieldset className="promo-filters" aria-label="Show">
        {counts.map(([key, label, n]) => (
          <button
            key={key}
            type="button"
            aria-pressed={filter === key}
            className={filter === key ? 'promo-pill is-on' : 'promo-pill'}
            onClick={() => setFilter(key)}
          >
            {`${label} · ${n}`}
          </button>
        ))}
      </fieldset>

      <div className="promo-layout">
        <div className="promo-main">
          {filter === 'candidates' &&
            (candidates.length === 0 ? (
              <p className="promo-empty">No facts have reached the team threshold yet.</p>
            ) : (
              candidates.map((item) => (
                <Candidate
                  key={item.id}
                  item={item}
                  open={isOpen(item.id)}
                  onToggle={() => toggle(item.id)}
                  threshold={status?.thresholds.candidate_at ?? 0}
                  onApprove={(edit) => act(api.approve(item.id, edit))}
                  onReject={() => act(api.reject(item.id))}
                />
              ))
            ))}

          {filter === 'flags' &&
            (flags.length === 0 ? (
              <p className="promo-empty">No team rule is being questioned.</p>
            ) : (
              flags.map((flag) => (
                <Flag
                  key={flag.id}
                  flag={flag}
                  rule={flag.rule_id ? rules.get(flag.rule_id) : undefined}
                  onKeep={() => act(api.keep(flag.id))}
                  onClose={() => act(api.close(flag.id))}
                />
              ))
            ))}

          {filter === 'decided' &&
            (decided.length === 0 ? (
              <p className="promo-empty">Nothing decided yet.</p>
            ) : (
              decided.map((item) => (
                <article
                  key={item.id}
                  className="promo-card promo-decided"
                  aria-label={title(item)}
                >
                  <div>
                    <h3>{title(item)}</h3>
                    <p className="promo-sub">
                      {DECISION_LABELS[item.status]} by {item.decided_by ?? '—'}
                      {item.decided_at
                        ? ` · ${day(item.decided_at)} ${time(item.decided_at)}`
                        : ''}
                      {item.status === 'active'
                        ? ` · ${item.entity}.${item.key} in the team scope`
                        : ''}
                    </p>
                  </div>
                  {item.status === 'active' && (
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={() => act(api.close(item.id))}
                    >
                      Close rule
                    </button>
                  )}
                </article>
              ))
            ))}

          {filter === 'groups' &&
            (groups.length === 0 ? (
              <p className="promo-empty">
                No topics yet. Run the job after people save facts.
              </p>
            ) : (
              groups.map((group) => <GroupCard key={group.id} group={group} />)
            ))}
        </div>

        <aside className="promo-side">
          {filter !== 'flags' &&
            flags.map((flag) => (
              <Flag
                key={flag.id}
                flag={flag}
                rule={flag.rule_id ? rules.get(flag.rule_id) : undefined}
                onKeep={() => act(api.keep(flag.id))}
                onClose={() => act(api.close(flag.id))}
              />
            ))}
          <section className="promo-card" aria-labelledby="promo-decided-title">
            <h3 id="promo-decided-title">Recently decided</h3>
            {decided.length === 0 ? (
              <p className="promo-empty">Nothing yet.</p>
            ) : (
              <dl className="promo-pairs">
                {decided.slice(0, 5).map((item) => (
                  <div key={item.id}>
                    <dt>{DECISION_LABELS[item.status]}</dt>
                    <dd>{title(item)}</dd>
                  </div>
                ))}
              </dl>
            )}
          </section>
          {status && (
            <section className="promo-card" aria-labelledby="promo-settings-title">
              <h3 id="promo-settings-title">Settings in use</h3>
              <dl className="promo-settings">
                <dt>personal rule at</dt>
                <dd>{num(status.thresholds.personal_rule_at)}</dd>
                <dt>candidate at</dt>
                <dd>{num(status.thresholds.candidate_at)}</dd>
                <dt>flag at</dt>
                <dd>{num(status.thresholds.flag_at)}</dd>
                <dt>repeat factor</dt>
                <dd>{num(status.thresholds.repeat_factor)}</dd>
                <dt>job every</dt>
                <dd>{status.enabled ? `${num(status.every_minutes / 60)} h` : 'off'}</dd>
              </dl>
            </section>
          )}
        </aside>
      </div>
    </section>
  )
}

function Chips({ values, current }: { values: ValueChip[]; current?: string }) {
  return (
    <div className="promo-chips">
      {values.map((v) => (
        <span
          key={v.value}
          className={v.value === current ? 'promo-chip is-on' : 'promo-chip'}
        >{`${v.value} · ${num(v.team_score)}`}</span>
      ))}
    </div>
  )
}

function EvidenceRows({ rows }: { rows: Evidence[] }) {
  return (
    <table className="promo-evidence">
      <tbody>
        {rows.map((row) => (
          <tr key={row.user}>
            <th scope="row">{person(row.user)}</th>
            <td className="promo-weights">{row.weights.map(num).join(' + ')}</td>
            <td>
              {row.said.length > 0 ? `“${row.said.at(-1)?.text ?? ''}”` : row.value}
            </td>
            <td className="promo-when">
              {[...new Set(row.said.map((s) => SOURCES[s.source] ?? s.source))].join(
                ', ',
              )}
              {row.said.length > 0 &&
                ` · ${row.said.map((s) => day(s.said_at)).join(', ')}`}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Candidate({
  item,
  open,
  onToggle,
  threshold,
  onApprove,
  onReject,
}: {
  item: ReviewItem
  open: boolean
  onToggle: () => void
  threshold: number
  onApprove: (edit: RuleEdit) => void
  onReject: () => void
}) {
  const [editing, setEditing] = useState(false)
  const fill =
    threshold > 0 ? Math.min(100, (item.team_score / (threshold * 1.25)) * 100) : 0
  const mark = threshold > 0 ? (1 / 1.25) * 100 : 0
  const panel = `promo-details-${item.id}`
  return (
    <article
      className={
        open ? 'promo-card promo-candidate is-open' : 'promo-card promo-candidate'
      }
      aria-label={title(item)}
    >
      <div className="promo-head">
        <div className="promo-title">
          <h3>{title(item)}</h3>
          <span className="promo-chip">{item.people} people</span>
        </div>
        {!open && <span className="promo-score-small">{num(item.team_score)}</span>}
        <button
          type="button"
          className="promo-toggle"
          aria-expanded={open}
          aria-controls={panel}
          aria-label={open ? 'Collapse' : 'Expand'}
          onClick={onToggle}
        >
          <svg viewBox="0 0 20 20" width="20" height="20" aria-hidden="true">
            <path
              d="M5 7.5 10 12.5 15 7.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </div>
      <div
        id={panel}
        className="promo-collapse"
        data-open={open}
        aria-hidden={!open}
        inert={!open}
      >
        <div className="promo-collapse-inner">
          <div className="promo-detail-head">
            <div>
              <p className="promo-sub">
                Group “{item.label}” · listed{' '}
                {item.created_at
                  ? `${day(item.created_at)} ${time(item.created_at)}`
                  : '—'}
              </p>
              <Chips values={item.values} current={item.value} />
            </div>
            <div className="promo-score">
              <strong>{num(item.team_score)}</strong>
              <span>{`team score · threshold ${num(threshold)}`}</span>
              <div className="promo-bar-track" aria-hidden="true">
                <div className="promo-bar-fill" style={{ width: `${fill}%` }} />
                <div className="promo-bar-mark" style={{ left: `${mark}%` }} />
              </div>
            </div>
          </div>
          <div className="promo-body">
            <h4>{`For · ${num(item.for_score)}`}</h4>
            <EvidenceRows rows={item.for_rows} />
            {item.against_rows.length > 0 && (
              <>
                <h4>{`Against · ${num(item.against_score)}`}</h4>
                <EvidenceRows rows={item.against_rows} />
              </>
            )}
          </div>
          <div className="promo-foot">
            {editing ? (
              <ApproveForm
                item={item}
                onCancel={() => setEditing(false)}
                onConfirm={onApprove}
              />
            ) : (
              <>
                <button type="button" className="btn" onClick={() => setEditing(true)}>
                  Approve as team rule
                </button>
                <button type="button" className="btn-secondary" onClick={onReject}>
                  Reject
                </button>
                <span className="promo-note">
                  Approving writes one knowledge fact to the team scope. Personal notes
                  stay as they are.
                </span>
              </>
            )}
          </div>
        </div>
      </div>
    </article>
  )
}

function Flag({
  flag,
  rule,
  onKeep,
  onClose,
}: {
  flag: ReviewItem
  rule?: ReviewItem
  onKeep: () => void
  onClose: () => void
}) {
  const id = `promo-flag-${flag.id}`
  const latest = flag.against_rows[0]
  const said = latest?.said[latest.said.length - 1]
  return (
    <section className="promo-card promo-flag" aria-labelledby={id}>
      <div className="promo-flag-head">
        <span className="promo-tag">Flag</span>
        <h3 id={id}>Differs from a team rule</h3>
      </div>
      <p>
        <b>Rule: </b>
        <span>{title(rule ?? flag)}</span>
      </p>
      {latest && (
        <p>
          {person(latest.user)} said <b>{latest.value}</b>
          {said
            ? ` in ${SOURCES[said.source] ?? said.source} · ${day(said.said_at)}`
            : ''}
        </p>
      )}
      <p className="promo-sub">
        {`Against · ${num(flag.against_score)}`}
        {flag.status === 'kept' ? ' · kept before' : ''}
      </p>
      <div className="promo-actions">
        {flag.status === 'open' && (
          <button type="button" className="btn-secondary" onClick={onKeep}>
            Keep rule
          </button>
        )}
        <button type="button" className="btn-secondary" onClick={onClose}>
          Close rule
        </button>
      </div>
    </section>
  )
}

function GroupCard({ group }: { group: Group }) {
  return (
    <article className="promo-card promo-folded" aria-label={group.label}>
      <h3>{group.label}</h3>
      <span className="promo-chip">{group.people} people</span>
      <Chips values={group.values} />
    </article>
  )
}

function ApproveForm({
  item,
  onCancel,
  onConfirm,
}: {
  item: ReviewItem
  onCancel: () => void
  onConfirm: (edit: RuleEdit) => void
}) {
  const [edit, setEdit] = useState<RuleEdit>({
    label: item.label,
    entity_type: item.entity_type,
    entity: item.entity,
    key: item.key,
    value: item.value,
  })
  const field = (name: keyof RuleEdit, label: string) => (
    <label>
      {label}
      <input
        value={edit[name]}
        onChange={(e) => setEdit({ ...edit, [name]: e.target.value })}
      />
    </label>
  )
  return (
    <form
      className="promo-form"
      onSubmit={(e) => {
        e.preventDefault()
        onConfirm(edit)
      }}
    >
      {field('label', 'Wording')}
      {field('entity_type', 'Entity type')}
      {field('entity', 'Entity')}
      {field('key', 'Key')}
      {field('value', 'Value')}
      <div className="promo-actions">
        <button type="submit" className="btn">
          Confirm
        </button>
        <button type="button" className="btn-secondary" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}
