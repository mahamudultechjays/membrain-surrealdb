import { useState, type ReactNode } from 'react'
import type {
  AskCompareResponse,
  AskConflict,
  AskFact,
  AskLayer,
  AskMode,
  AskResponse,
  FactProvenance,
} from '@/api/ask'
import FactRow from '@/components/ask/FactRow'
import { LayerMark, ModeGlyph } from '@/components/ask/LayerGlyph'
import TrustChip from '@/components/ask/TrustChip'
import {
  formatScore,
  LAYER_LABELS,
  MODE_HINTS,
  MODE_LABELS,
} from '@/components/ask/layers'

interface Props {
  /** Both modes, from one recall. */
  answer: AskCompareResponse
  /** Whose grants were read, e.g. "Priya". */
  who: string
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

/**
 * Both modes answer the same question side by side. The table on top lines up
 * each point the layers disagree on: the value Best match used next to every
 * value By layer found. Under it, each mode's full answer in its own column.
 */
export default function AskAnswer({ answer, who }: Props) {
  const { q, best_match: best, by_layer: byLayer } = answer
  return (
    <section className="ask-answer" aria-labelledby="ask-answer-heading">
      <header className="ask-answer-head">
        <h2 id="ask-answer-heading">{q}</h2>
        <span className="mono ask-summary">
          {plural(best.layers.length, 'layer')} read once · tier{' '}
          {best.metadata.resolution_tier ?? 'none'} ·{' '}
          {best.metadata.latency_ms.toLocaleString('en')} ms · as {who}
        </span>
      </header>

      <CompareTable best={best} byLayer={byLayer} />

      <div className="ask-columns">
        <Column mode="best_match" answer={best}>
          <LayerTally layers={best.layers} />
          <FactList answer={best} />
        </Column>
        <Column mode="by_layer" answer={byLayer}>
          <LayerCards layers={byLayer.layers} />
        </Column>
      </div>

      <footer className="mono ask-footer">
        <span>trace {best.trace_id ?? 'none'}</span>
        {best.metadata.trace_ids.length > 0 && (
          <span>layer traces {best.metadata.trace_ids.join(', ')}</span>
        )}
        <span>answered {best.answered_at}</span>
      </footer>
    </section>
  )
}

interface Row {
  key: string
  entity: string
  point: string
  best: AskConflict | null
  byLayer: AskConflict | null
}

/** The same point in both answers, matched on entity and key, in first-seen order. */
function rowsOf(best: AskResponse, byLayer: AskResponse): Row[] {
  const rows = new Map<string, Row>()
  const add = (conflict: AskConflict, side: 'best' | 'byLayer') => {
    const key = `${conflict.entity}\u0000${conflict.key}`.toLowerCase()
    const row = rows.get(key) ?? {
      key,
      entity: conflict.entity,
      point: conflict.key,
      best: null,
      byLayer: null,
    }
    row[side] = conflict
    rows.set(key, row)
  }
  best.conflicts.forEach((c) => add(c, 'best'))
  byLayer.conflicts.forEach((c) => add(c, 'byLayer'))
  return [...rows.values()]
}

/** One row per disagreement: what Best match used, and every value By layer found. */
function CompareTable({ best, byLayer }: { best: AskResponse; byLayer: AskResponse }) {
  const rows = rowsOf(best, byLayer)
  if (!rows.length) {
    return (
      <p className="ask-muted ask-no-conflict">
        No disagreements between layers, so both modes show the same facts. Only facts
        stored as a key and value are compared.
      </p>
    )
  }
  return (
    <div className="ask-compare-wrap">
      <table className="ask-compare">
        <caption>
          <DisagreeIcon />
          {plural(rows.length, 'point')} where the layers disagree
        </caption>
        <thead>
          <tr>
            <th scope="col">Point</th>
            <th scope="col">
              <ModeGlyph mode="best_match" />
              {MODE_LABELS.best_match}
            </th>
            <th scope="col">
              <ModeGlyph mode="by_layer" />
              {MODE_LABELS.by_layer}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <th scope="row" data-label="Point">
                <span className="ask-compare-entity">{row.entity}</span>
                <span className="mono ask-compare-key">{row.point}</span>
              </th>
              <td data-label={MODE_LABELS.best_match}>
                <Picked conflict={row.best} answer={best} />
              </td>
              <td data-label={MODE_LABELS.by_layer}>
                <AllValues conflict={row.byLayer} answer={byLayer} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** The value Best match used for this point, where it came from, and why. */
function Picked({
  conflict,
  answer,
}: {
  conflict: AskConflict | null
  answer: AskResponse
}) {
  if (!conflict) return <NotFlagged />
  const winner = conflict.values.find((v) =>
    v.hit_ids.includes(conflict.winner_hit_id ?? ''),
  )
  const layer = answer.layers.find((l) =>
    l.facts.some((f) => f.source.hit_id === conflict.winner_hit_id),
  )
  if (!winner) return <NotFlagged />
  return (
    <div className="ask-picked">
      <span className="ask-picked-value">
        <span className="mono ask-value-text">{winner.value}</span>
        {layer && (
          <span className="tag ask-layer-tag" title={layer.area}>
            <LayerMark layer={layer.layer} />
            {LAYER_LABELS[layer.layer]}
          </span>
        )}
        <span className="tag" data-tone="good">
          Used
        </span>
        <ValueTrust hitIds={[conflict.winner_hit_id ?? '']} answer={answer} />
      </span>
      {conflict.reason && <span className="ask-picked-reason">{conflict.reason}</span>}
    </div>
  )
}

/** Every value By layer found for this point, with its layers; none chosen. */
function AllValues({
  conflict,
  answer,
}: {
  conflict: AskConflict | null
  answer: AskResponse
}) {
  if (!conflict) return <NotFlagged />
  return (
    <ul className="ask-all-values">
      {conflict.values.map((v) => (
        <li key={v.value}>
          <span className="mono ask-value-text">{v.value}</span>
          <span className="ask-value-meta">
            {v.layers
              .map((l) => LAYER_LABELS[l as keyof typeof LAYER_LABELS] ?? l)
              .join(', ')}
            <span className="mono">match {formatScore(v.best_score)}</span>
            <ValueTrust hitIds={v.hit_ids} answer={answer} />
          </span>
        </li>
      ))}
    </ul>
  )
}

/** The most trusted of the hits holding a value, so a value reads by its best source. */
function ValueTrust({ hitIds, answer }: { hitIds: string[]; answer: AskResponse }) {
  const found = answer.layers
    .flatMap((l) => l.facts)
    .filter((f) => hitIds.includes(f.source.hit_id))
    .map((f) => f.source.provenance)
    .filter((p): p is FactProvenance => p?.trust != null)
    .sort((a, b) => (b.trust ?? 0) - (a.trust ?? 0))[0]
  return found ? <TrustChip provenance={found} /> : null
}

/** Both modes see the same hits, so this is a guard rather than an expected state. */
function NotFlagged() {
  return <span className="ask-muted">Not flagged in this mode</span>
}

/** Two paths leaving one point: the same fact going two ways. */
function DisagreeIcon() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" fill="none" aria-hidden="true">
      <path
        d="M2.5 8h4.2M6.7 8l5-4M6.7 8l5 4"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="12.6" cy="3.4" r="1.6" fill="currentColor" />
      <circle cx="12.6" cy="12.6" r="1.6" fill="currentColor" />
    </svg>
  )
}

/** One mode's column: its name, what it does, then its answer. */
function Column({
  mode,
  answer,
  children,
}: {
  mode: AskMode
  answer: AskResponse
  children: ReactNode
}) {
  const headingId = `ask-col-${mode}`
  return (
    <section className="ask-column" aria-labelledby={headingId} data-mode={mode}>
      <header className="ask-column-head">
        <h3 id={headingId}>
          <ModeGlyph mode={mode} />
          {MODE_LABELS[mode]}
        </h3>
        <span className="mono ask-column-meta">
          {plural(answer.metadata.total_facts, 'fact')}
        </span>
        <p className="ask-column-hint">{MODE_HINTS[mode]}</p>
      </header>
      {children}
    </section>
  )
}

interface Placed {
  fact: AskFact
  layer: AskLayer
}

/** How many facts each layer gave, and any layer whose recall failed. */
function LayerTally({ layers }: { layers: AskLayer[] }) {
  const failed = layers.filter((l) => l.error)
  return (
    <>
      <p className="ask-tally">
        {layers.map((l) => (
          <span key={`${l.layer}:${l.area}`} className="ask-tally-item" title={l.area}>
            <LayerMark layer={l.layer} />
            {LAYER_LABELS[l.layer]}
            <span className="mono">{l.error ? 'failed' : l.facts.length}</span>
          </span>
        ))}
      </p>
      {failed.map((l) => (
        <p key={l.area} className="error ask-tally-error">
          Recall failed for {LAYER_LABELS[l.layer]} {l.area}: {l.error}
        </p>
      ))}
    </>
  )
}

/**
 * Best match as one list across layers: each value it used first, with the
 * values it set aside folded under it; everything else follows by match score.
 */
function FactList({ answer }: { answer: AskResponse }) {
  const placed: Placed[] = answer.layers.flatMap((layer) =>
    layer.facts.map((fact) => ({ fact, layer })),
  )
  const byScore = (a: Placed, b: Placed) => b.fact.source.score - a.fact.source.score

  if (!placed.length) {
    return <p className="empty">Nothing found in the spaces searched.</p>
  }

  const winners = answer.conflicts
    .map((c) => placed.find((p) => p.fact.source.hit_id === c.winner_hit_id))
    .filter((p): p is Placed => Boolean(p))
  const winnerIds = new Set(winners.map((p) => p.fact.source.hit_id))
  const asideOf = (conflictId: string | null | undefined) =>
    placed.filter(
      (p) => p.fact.status === 'set_aside' && p.fact.conflict_id === conflictId,
    )
  const rest = placed
    .filter((p) => !winnerIds.has(p.fact.source.hit_id) && p.fact.status !== 'set_aside')
    .sort(byScore)

  return (
    <ul className="ask-facts ask-flat">
      {winners.map((p) => (
        <FactRow
          key={p.fact.source.hit_id}
          fact={p.fact}
          layer={p.layer}
          aside={asideOf(p.fact.conflict_id)}
        />
      ))}
      {rest.map((p) => (
        <FactRow key={p.fact.source.hit_id} fact={p.fact} layer={p.layer} />
      ))}
    </ul>
  )
}

/**
 * By layer: one card per layer, closed to start. The table above already shows
 * what differs; each header keeps the count and how many of its facts
 * disagree, so a closed card still says whether it is worth opening.
 */
function LayerCards({ layers }: { layers: AskLayer[] }) {
  // Remounting with a new key applies "expand all" or "collapse all" to every card.
  const [all, setAll] = useState<{ open: boolean; round: number }>({
    open: false,
    round: 0,
  })
  return (
    <div className="ask-layer-cards">
      <div className="ask-layer-tools">
        <button
          type="button"
          className="ask-layer-toggle"
          onClick={() => setAll((s) => ({ open: !s.open, round: s.round + 1 }))}
        >
          {all.open ? 'Collapse all' : 'Expand all'}
        </button>
      </div>
      {layers.map((layer) => (
        <LayerSection
          key={`${layer.layer}:${layer.area}:${all.round}`}
          layer={layer}
          open={all.open}
        />
      ))}
    </div>
  )
}

function LayerSection({ layer, open }: { layer: AskLayer; open: boolean }) {
  const disagree = layer.facts.filter((f) => f.conflict_id).length
  return (
    <details
      className="ask-layer"
      data-layer={layer.layer}
      aria-label={`${LAYER_LABELS[layer.layer]} ${layer.area}`}
      open={open || undefined}
    >
      <summary className="ask-layer-head">
        <h4>
          <LayerMark layer={layer.layer} />
          {LAYER_LABELS[layer.layer]} <span className="mono ask-area">{layer.area}</span>
          {layer.layer === 'personal' && layer.owner && (
            <span className="ask-owner"> · {layer.owner}</span>
          )}
        </h4>
        <span className="ask-layer-badges">
          {layer.error && (
            <span className="tag" data-tone="bad">
              Failed
            </span>
          )}
          {disagree > 0 && (
            <span className="tag" data-tone="warn">
              {disagree} disagree
            </span>
          )}
          <span className="mono ask-count">{layer.facts.length}</span>
          <svg
            className="ask-layer-chevron"
            viewBox="0 0 16 16"
            width="14"
            height="14"
            fill="none"
            aria-hidden="true"
          >
            <path
              d="M4 6l4 4 4-4"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
      </summary>
      {/* One layer failing still lets the others answer. */}
      {layer.error ? (
        <p className="error">Recall failed for this layer: {layer.error}</p>
      ) : layer.facts.length === 0 ? (
        <p className="ask-muted">Nothing found in {layer.area}</p>
      ) : (
        <ul className="ask-facts">
          {layer.facts.map((fact) => (
            <FactRow key={fact.source.hit_id} fact={fact} />
          ))}
        </ul>
      )}
    </details>
  )
}
