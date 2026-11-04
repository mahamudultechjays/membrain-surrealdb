import { useEffect, useRef, useState, type FormEvent } from 'react'
import { askApi, type AskApi, type AskResponse } from '@/api/ask'
import type { Me } from '@/api/auth'
import type { ChatApi } from '@/api/chat'
import { ApiError } from '@/api/client'
import AskAnswer from '@/components/ask/AskAnswer'
import AskChat from '@/components/ask/AskChat'
import AskLoading from '@/components/ask/AskLoading'
import { readAreas, spaceName } from '@/components/ask/layers'
import HeaderSlot from '@/components/HeaderSlot'
import { useHashSubRoute } from '@/hooks/useHashRoute'
import ScopePicker from '@/components/ScopePicker'
import '@/pages/ask.css'

/** Questions that hit the mock seed data, so the demo always has something to show. */
const QUICK_PICKS = [
  'What is the returns window?',
  'What do we know about Acme Logistics?',
  'Is dock 3 open?',
  'Who is on call for checkout?',
]

type Run =
  | { status: 'idle' }
  | { status: 'cancelled' }
  /** `id` remounts the loading timer for each new question. */
  | { status: 'loading'; id: number }
  /** `who` is fixed when asked, so changing the picker later can't relabel it. */
  | { status: 'success'; answer: AskResponse; who: string }
  | { status: 'error'; error: Error }

interface Props {
  me: Me
  api?: AskApi
}

const MODES = ['search', 'chat'] as const
type Mode = (typeof MODES)[number]
const MODE_LABELS: Record<Mode, string> = { search: 'Search', chat: 'Chat' }
const MODE_INTROS: Record<Mode, string> = {
  search:
    'Answers come from every scope you can read: org first, then team, then personal. Asking never writes.',
  chat: 'A written answer from every scope you can read, citing its sources. Follow-ups keep the context.',
}

/** Ask has two modes, each with its own URL: #/ask/search and #/ask/chat. */
export default function AskPage({
  me,
  api = askApi,
  chatApi,
}: Props & { chatApi?: ChatApi }) {
  const mode = useHashSubRoute(MODES, 'search')
  return (
    <main className="page ask-page">
      <div className="page-head">
        <h1>Ask</h1>
        <nav className="ask-modes" aria-label="Ask mode">
          {MODES.map((m) => (
            <a key={m} href={`#/ask/${m}`} aria-current={m === mode ? 'page' : undefined}>
              {MODE_LABELS[m]}
            </a>
          ))}
        </nav>
        <p>{MODE_INTROS[mode]}</p>
      </div>
      {mode === 'chat' ? (
        <AskChat me={me} api={chatApi} />
      ) : (
        <AskSearch me={me} api={api} />
      )}
    </main>
  )
}

function AskSearch({ me, api = askApi }: Props) {
  // Spaces left out of the search. Everything is searched until the user
  // unticks something, so a newly granted space is included straight away.
  const [excluded, setExcluded] = useState<string[]>([])
  const [question, setQuestion] = useState('')
  const [run, setRun] = useState<Run>({ status: 'idle' })
  const inFlight = useRef<AbortController | null>(null)
  const runCount = useRef(0)

  // A slow recall must never land on an unmounted page.
  useEffect(() => () => inFlight.current?.abort(), [])

  // Every space this user may read, org first, each named by whose it is.
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
  const who = me.name

  const ask = (q: string) => {
    const text = q.trim()
    // No scopes would mean "read everything" to the backend, so never send that.
    if (!text || !areas.length) return
    // A new question replaces the old one; its answer would be stale.
    inFlight.current?.abort()
    const controller = new AbortController()
    inFlight.current = controller
    setRun({ status: 'loading', id: ++runCount.current })
    const askedAs = who
    api
      .ask({ q: text, scopes: narrowed }, controller.signal)
      .then((answer) => {
        if (!controller.signal.aborted)
          setRun({ status: 'success', answer, who: askedAs })
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setRun({
          status: 'error',
          error: error instanceof Error ? error : new Error(String(error)),
        })
      })
  }

  const cancel = () => {
    inFlight.current?.abort()
    setRun({ status: 'cancelled' })
  }

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    ask(question)
  }

  const pick = (q: string) => {
    setQuestion(q)
    ask(q)
  }

  return (
    <>
      <section className="panel ask-who" aria-label="Spaces searched">
        {options.length > 1 && (
          <HeaderSlot>
            <ScopePicker
              multiple
              label="Search in"
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
      </section>

      <form className="ask-form" onSubmit={onSubmit}>
        <label htmlFor="ask-question" className="ask-label">
          Question
        </label>
        <div className="ask-input-row">
          <input
            id="ask-question"
            type="search"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="What is the returns window?"
            autoComplete="off"
          />
          <button
            type="submit"
            className="btn"
            disabled={!question.trim() || !areas.length}
          >
            Ask
          </button>
        </div>
        <fieldset className="ask-chips ask-quick">
          <legend className="visually-hidden">Quick questions</legend>
          {QUICK_PICKS.map((q) => (
            <button
              key={q}
              type="button"
              className="ask-chip"
              disabled={!areas.length}
              onClick={() => pick(q)}
            >
              {q}
            </button>
          ))}
        </fieldset>
      </form>

      <div className="ask-result">
        {run.status === 'idle' && (
          <p className="empty">
            Pick a question or type one. Answers respect what each person can read.
          </p>
        )}
        {run.status === 'cancelled' && (
          <p className="empty">Cancelled. Ask again when ready.</p>
        )}
        {run.status === 'loading' && <AskLoading key={run.id} onCancel={cancel} />}
        {run.status === 'error' && <AskFailure error={run.error} />}
        {run.status === 'success' && <AskAnswer answer={run.answer} who={run.who} />}
      </div>
    </>
  )
}

/** FastAPI's `detail` is already in the message; add a hint for the statuses we expect. */
function AskFailure({ error }: { error: Error }) {
  const status = error instanceof ApiError ? error.status : null
  const hint =
    status === 403
      ? 'One of the chosen spaces is not one you can read.'
      : status === 503
        ? 'Every layer failed to answer. Agent Memory may be down; try again shortly.'
        : null
  return (
    <div className="error" role="alert">
      <p className="ask-error-message">{error.message}</p>
      {hint && <p className="ask-error-hint">{hint}</p>}
    </div>
  )
}
