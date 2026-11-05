import { useRef, useState, type FormEvent } from 'react'
import type { Me } from '@/api/auth'
import { reflectApi, type ReflectApi, type ReflectLayer } from '@/api/reflect'
import { LAYER_LABELS, readAreas, spaceName } from '@/components/ask/layers'
import {
  updateReflections,
  useReflections,
  type Reflection,
} from '@/components/ask/reflectStore'
import ReplyText from '@/components/ask/ReplyText'
import HeaderSlot from '@/components/HeaderSlot'
import ScopePicker from '@/components/ScopePicker'

/** Unique across visits to the page, since reflections outlive the component. */
const newId = () => `r${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`

interface Props {
  me: Me
  api?: ReflectApi
}

/**
 * Ask in reflect mode: a synthesis across every space the user can read, with
 * the evidence it drew on. Each question stands alone and nothing is saved:
 * the answer is the model's own conclusion, so the page says to check it.
 */
export default function AskReflect({ me, api = reflectApi }: Props) {
  const [excluded, setExcluded] = useState<string[]>([])
  const [question, setQuestion] = useState('')
  const owner = me.email
  const reflections = useReflections(owner)
  const inFlight = useRef<AbortController | null>(null)

  const readable = readAreas(me.grants).map((path) =>
    me.grants.find((g) => g.scope_path === path)!,
  )
  const options = readable.map((g) => ({
    id: g.scope_path,
    name: spaceName(g),
    detail: g.scope_path,
  }))
  const areas = readable.map((g) => g.scope_path).filter((p) => !excluded.includes(p))
  // Narrow the backend only when something is left out; otherwise it reads all.
  const narrowed = areas.length < readable.length ? areas : []
  const busy = reflections.some((r) => r.status === 'loading')

  /** Replaces reflection `id`, if it is still there (Clear may have removed it). */
  const settle = (next: Reflection) =>
    updateReflections(owner, (list) => list.map((r) => (r.id === next.id ? next : r)))

  const ask = (event: FormEvent) => {
    event.preventDefault()
    const text = question.trim()
    if (!text || !areas.length || busy) return
    const controller = new AbortController()
    inFlight.current = controller
    const id = newId()
    // Newest first: each question stands alone, so the latest answer leads.
    updateReflections(owner, (list) => [
      { id, question: text, status: 'loading' },
      ...list,
    ])
    setQuestion('')
    api
      .ask({ question: text, scopes: narrowed }, controller.signal)
      .then((response) => {
        if (!controller.signal.aborted)
          settle({ id, question: text, status: 'done', response })
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        settle({
          id,
          question: text,
          status: 'error',
          message: error instanceof Error ? error.message : String(error),
        })
      })
  }

  const cancel = () => {
    inFlight.current?.abort()
    updateReflections(owner, (list) =>
      list.map((r) =>
        r.status === 'loading'
          ? { id: r.id, question: r.question, status: 'cancelled' }
          : r,
      ),
    )
  }

  const clear = () => {
    inFlight.current?.abort()
    updateReflections(owner, () => [])
  }

  return (
    <div className="ask-reflect">
      <section className="panel ask-who" aria-label="Spaces the reflection draws on">
        {options.length > 1 && (
          <HeaderSlot>
            <ScopePicker
              multiple
              label="Reflect on"
              allLabel="All spaces"
              options={options}
              value={areas}
              onChange={(ids) =>
                setExcluded(options.map((o) => o.id).filter((id) => !ids.includes(id)))
              }
            />
          </HeaderSlot>
        )}
        <p className="mono ask-muted ask-reads">
          Reads {areas.length ? areas.join(' → ') : 'nothing: tick at least one space'}
        </p>
        <p className="ask-muted chat-note">
          A reflection is the model’s own conclusion across your spaces, so check it
          against the evidence listed under it. Nothing is saved.
        </p>
      </section>

      <form className="ask-form" onSubmit={ask}>
        <label htmlFor="ask-reflect-question" className="ask-label">
          Question
        </label>
        <div className="ask-input-row">
          <input
            id="ask-reflect-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="What patterns do we see across our carriers?"
            autoComplete="off"
          />
          <button
            type="submit"
            className="btn"
            disabled={!question.trim() || !areas.length || busy}
          >
            Reflect
          </button>
          <button
            type="button"
            className="btn-secondary"
            disabled={!reflections.length}
            onClick={clear}
          >
            Clear
          </button>
        </div>
      </form>

      <div className="chat-log" aria-live="polite">
        {reflections.map((r) => (
          <div key={r.id} className="reflect-entry">
            <p className="chat-question">{r.question}</p>
            {r.status === 'loading' && (
              <div className="panel ask-loading">
                <span className="ask-spinner" aria-hidden="true" />
                <output className="ask-loading-text">
                  <strong>Reflecting…</strong>
                  <span className="ask-muted">
                    Reasoning across your spaces, about 20 s.
                  </span>
                </output>
                <button type="button" className="btn-secondary" onClick={cancel}>
                  Cancel
                </button>
              </div>
            )}
            {r.status === 'cancelled' && <p className="empty">Cancelled.</p>}
            {r.status === 'error' && (
              <div className="error" role="alert">
                <p className="ask-error-message">{r.message}</p>
              </div>
            )}
            {r.status === 'done' && (
              <article
                className="panel chat-answer reflect-answer"
                aria-label={`Reflection on ${r.question}`}
              >
                {r.response.layers.map((layer) => (
                  <LayerReflectionCard key={layer.scope} layer={layer} />
                ))}
              </article>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

/** One layer's own reflection: what this scope alone says, and its evidence. */
function LayerReflectionCard({ layer }: { layer: ReflectLayer }) {
  const name = LAYER_LABELS[layer.layer]
  return (
    <section className="reflect-layer" aria-label={`${name} reflection`}>
      <p className="reflect-layer-head">
        <strong>{name}</strong> <span className="mono ask-muted">{layer.scope}</span>
      </p>
      {layer.status === 'failed' ? (
        <p className="ask-muted">{layer.error}</p>
      ) : (
        <>
          {layer.answer && (
            <div className="chat-reply">
              <ReplyText text={layer.answer} marker={(label) => `[${label}]`} />
            </div>
          )}
          {layer.evidence.length > 0 && (
            <ol className="chat-sources" aria-label="Evidence">
              {layer.evidence.map((item, i) => (
                <li key={i}>
                  <span className="chat-source-marker mono">{i + 1}</span>
                  <span className="chat-source-body">{item}</span>
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </section>
  )
}
