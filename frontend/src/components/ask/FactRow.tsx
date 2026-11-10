import { useEffect, useId, useRef, useState } from 'react'
import type { AskFact, AskLayer, FactProvenance } from '@/api/ask'
import { LayerMark } from '@/components/ask/LayerGlyph'
import {
  formatDate,
  formatScore,
  LAYER_LABELS,
  SOURCE_KIND_LABELS,
} from '@/components/ask/layers'
import TrustChip from '@/components/ask/TrustChip'

interface Placed {
  fact: AskFact
  layer: AskLayer
}

interface Props {
  fact: AskFact
  /** In the single-list modes, the layer this fact came from, shown as a label. */
  layer?: AskLayer
  /** Best match: the values this fact won over, folded under it. */
  aside?: Placed[]
}

/**
 * One recalled fact. The score button opens its source inline, below the row:
 * a disclosure rather than a modal, so it reads well at 375px and keeps the
 * fact in view. Focus moves into the panel on open and back on Escape.
 *
 * Best match marks a fact in a conflict as used or set aside, with its reason;
 * By layer only marks that it is part of a conflict. Default marks nothing.
 */
export default function FactRow({ fact, layer, aside = [] }: Props) {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLElement>(null)
  const factId = useId()
  const panelId = useId()
  const { source } = fact
  const setAside = fact.status === 'set_aside'

  const close = () => {
    setOpen(false)
    triggerRef.current?.focus()
  }

  // Focus the panel on open, and let Escape close it from anywhere inside. A
  // native listener, since jsx-a11y rejects key handlers on a <section> even
  // when, like here, it is focusable.
  useEffect(() => {
    const panel = panelRef.current
    if (!open || !panel) return
    panel.focus()
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.stopPropagation()
      setOpen(false)
      triggerRef.current?.focus()
    }
    panel.addEventListener('keydown', onKeyDown)
    return () => panel.removeEventListener('keydown', onKeyDown)
  }, [open])

  return (
    <li className="ask-fact" data-status={fact.status ?? undefined}>
      <div className="ask-fact-row">
        <span id={factId} className="mono ask-fact-text">
          {fact.fact}
        </span>
        <span className="ask-fact-meta">
          {layer && <LayerTag layer={layer} />}
          {/* The verdict leads, nearest the fact it is about. */}
          {fact.status === 'used' && (
            <span className="tag ask-fact-state" data-tone="good">
              Used
            </span>
          )}
          {setAside && <span className="tag ask-fact-state">Set aside</span>}
          {!fact.status && fact.conflict_id && (
            <span className="tag ask-fact-state" data-tone="warn">
              Layers disagree
            </span>
          )}
          {source.provenance && <TrustChip provenance={source.provenance} />}
          <span
            className="tag"
            data-tone={source.kind === 'document' ? 'note' : undefined}
          >
            {source.kind}
          </span>
          <span className="tag">{source.hit_kind}</span>
          <button
            ref={triggerRef}
            type="button"
            className="ask-score"
            aria-expanded={open}
            aria-controls={panelId}
            aria-describedby={factId}
            onClick={() => (open ? close() : setOpen(true))}
          >
            match score <span className="mono">{formatScore(source.score)}</span>
          </button>
        </span>
      </div>
      {fact.reason && (
        <p className="ask-fact-reason" data-status={fact.status ?? undefined}>
          {fact.reason}
        </p>
      )}
      {aside.length > 0 && (
        <details className="ask-aside">
          <summary>{aside.length} set aside</summary>
          <ul>
            {aside.map((a) => (
              <li key={a.fact.source.hit_id}>
                <span className="mono ask-aside-text">{a.fact.fact}</span>
                <span className="ask-aside-meta">
                  <LayerTag layer={a.layer} />
                  {a.fact.source.provenance && (
                    <TrustChip provenance={a.fact.source.provenance} />
                  )}
                  <span className="mono">match {formatScore(a.fact.source.score)}</span>
                </span>
                {a.fact.reason && <p className="ask-aside-reason">{a.fact.reason}</p>}
              </li>
            ))}
          </ul>
        </details>
      )}
      {open && (
        <section
          ref={panelRef}
          id={panelId}
          aria-label="Source"
          tabIndex={-1}
          className="ask-source"
        >
          <div className="ask-source-head">
            <strong>Source</strong>
            <button
              type="button"
              className="btn-secondary ask-source-close"
              onClick={close}
            >
              Close
            </button>
          </div>
          <dl>
            <dt>Kind</dt>
            <dd>{source.kind}</dd>
            <dt>Hit kind</dt>
            <dd>{source.hit_kind}</dd>
            <dt>Hit id</dt>
            <dd className="mono">{source.hit_id}</dd>
            <dt>Match score</dt>
            <dd className="mono">{formatScore(source.score)}</dd>
            {source.provenance && <ProvenanceRows provenance={source.provenance} />}
            {source.occurred_at && (
              <>
                <dt>Happened</dt>
                <dd>{formatDate(source.occurred_at)}</dd>
              </>
            )}
            {/* Always null today; shown as soon as the backend fills them. */}
            {source.title && (
              <>
                <dt>Title</dt>
                <dd>{source.title}</dd>
              </>
            )}
            {source.date && (
              <>
                <dt>Date</dt>
                <dd>{source.date}</dd>
              </>
            )}
            {/* The hit's own text, not a verified quote, so it is not styled as one. */}
            <dt>Hit text</dt>
            <dd className="mono">{source.text}</dd>
          </dl>
          <p className="ask-muted">
            Agent Memory recall returns no document title or position yet.
          </p>
        </section>
      )}
    </li>
  )
}

/** Org, Team or Personal, with the layer stack mark; the scope path on hover. */
function LayerTag({ layer }: { layer: AskLayer }) {
  return (
    <span className="tag ask-layer-tag" title={layer.area}>
      <LayerMark layer={layer.layer} />
      {LAYER_LABELS[layer.layer]}
    </span>
  )
}

/** Trust, how the fact was written, and its history, in the Source panel. */
function ProvenanceRows({ provenance: p }: { provenance: FactProvenance }) {
  const valid = [p.valid_from, p.valid_until].some(Boolean)
    ? `${p.valid_from ? formatDate(p.valid_from) : 'always'} to ${p.valid_until ? formatDate(p.valid_until) : 'now'}`
    : null
  return (
    <>
      {p.trust != null && (
        <>
          <dt>Trust</dt>
          <dd className="mono">{formatScore(p.trust)}</dd>
        </>
      )}
      {p.confidence != null && (
        <>
          <dt>Confidence</dt>
          <dd className="mono">{formatScore(p.confidence)}</dd>
        </>
      )}
      {p.source_kind && (
        <>
          <dt>Written as</dt>
          <dd>{SOURCE_KIND_LABELS[p.source_kind] ?? p.source_kind}</dd>
        </>
      )}
      {p.created_at && (
        <>
          <dt>Added</dt>
          <dd>{formatDate(p.created_at)}</dd>
        </>
      )}
      {valid && (
        <>
          <dt>Valid</dt>
          <dd>{valid}</dd>
        </>
      )}
      {p.superseded_by && (
        <>
          <dt>Replaced by</dt>
          <dd className="mono">{p.superseded_by}</dd>
        </>
      )}
    </>
  )
}
