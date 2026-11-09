import { useEffect, useId, useRef, useState } from 'react'
import type { AskFact } from '@/api/ask'
import type { FactTags, VctApi } from '@/api/vct'
import { formatScore } from '@/components/ask/layers'
import { TagEditor, VctTags } from '@/components/vct/Vct'

/**
 * One recalled fact. The score button opens its source inline, below the row:
 * a disclosure rather than a modal, so it reads well at 375px and keeps the
 * fact in view. Focus moves into the panel on open and back on Escape.
 */
export default function FactRow({ fact, vctApi }: { fact: AskFact; vctApi?: VctApi }) {
  const [open, setOpen] = useState(false)
  // Only facts (attribute hits) carry VCT tags; edits update the chips at once.
  const taggable = fact.source.hit_kind === 'attribute'
  const [tags, setTags] = useState<FactTags | null | undefined>(fact.tags)
  const [editing, setEditing] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLElement>(null)
  const factId = useId()
  const panelId = useId()
  const { source } = fact

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
    <li className="ask-fact">
      <div className="ask-fact-row">
        <span id={factId} className="mono ask-fact-text">
          {fact.fact}
        </span>
        <span className="ask-fact-meta">
          <VctTags tags={tags} />
          {taggable && (
            <button
              type="button"
              className="ask-score"
              aria-expanded={editing}
              onClick={() => setEditing(!editing)}
            >
              {editing ? 'Close tags' : 'Edit tags'}
            </button>
          )}
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
      {editing && (
        <TagEditor factId={fact.source.hit_id} api={vctApi} onChange={setTags} />
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
