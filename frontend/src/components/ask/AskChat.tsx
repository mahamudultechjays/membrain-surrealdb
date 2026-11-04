import {
  Fragment,
  useId,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type MouseEvent,
} from 'react'
import type { Me } from '@/api/auth'
import { chatApi, type ChatApi, type ChatCitation, type ChatResponse } from '@/api/chat'
import { ApiError } from '@/api/client'
import { updateChat, useChat, type Turn } from '@/components/ask/chatStore'
import { formatScore, readAreas, spaceName } from '@/components/ask/layers'
import ReplyText from '@/components/ask/ReplyText'
import HeaderSlot from '@/components/HeaderSlot'
import ScopePicker from '@/components/ScopePicker'

/** Unique across visits to the page, since turns outlive the component. */
const newTurnId = () =>
  `t${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`

interface Props {
  me: Me
  api?: ChatApi
}

/**
 * Ask in chat mode: a conversation whose answers cite their sources inline.
 * Agent Memory stores each question in the user's own space, so the page says so.
 */
export default function AskChat({ me, api = chatApi }: Props) {
  const [excluded, setExcluded] = useState<string[]>([])
  const [draft, setDraft] = useState('')
  // The conversation lives in the store, so it survives leaving this page; a
  // reply still on its way when the user leaves lands there too.
  const owner = me.email
  const { turns, sessionId } = useChat(owner)
  const inFlight = useRef<AbortController | null>(null)
  const prefix = useId().replace(/[^a-zA-Z0-9_-]/g, '')

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
  const personal = me.grants.find((g) => g.layer === 'personal' && g.access === 'write')
  const busy = turns.some((t) => t.status === 'loading')

  /** Replaces turn `id`, if it is still there (New chat may have cleared it). */
  const settle = (id: string, next: Turn, sessionAfter?: string | null) =>
    updateChat(owner, (state) => {
      if (!state.turns.some((t) => t.id === id)) return state
      return {
        turns: state.turns.map((t) => (t.id === id ? next : t)),
        sessionId: sessionAfter === undefined ? state.sessionId : sessionAfter,
      }
    })

  const send = (text: string) => {
    const message = text.trim()
    if (!message || !areas.length || busy) return
    const controller = new AbortController()
    inFlight.current = controller
    const id = newTurnId()
    updateChat(owner, (state) => ({
      ...state,
      turns: [...state.turns, { id, question: message, status: 'loading' }],
    }))
    setDraft('')
    api
      .send({ message, session_id: sessionId, scopes: narrowed }, controller.signal)
      .then((response) => {
        if (controller.signal.aborted) return
        settle(
          id,
          { id, question: message, status: 'done', response },
          response.session_id,
        )
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        const status = error instanceof ApiError ? error.status : null
        settle(
          id,
          {
            id,
            question: message,
            status: 'error',
            message: error instanceof Error ? error.message : String(error),
            hint: hintFor(status),
          },
          // The server forgets sessions on restart; the next message starts afresh.
          status === 404 ? null : undefined,
        )
      })
  }

  const cancel = () => {
    inFlight.current?.abort()
    updateChat(owner, (state) => ({
      ...state,
      turns: state.turns.map((t) =>
        t.status === 'loading'
          ? { id: t.id, question: t.question, status: 'cancelled' }
          : t,
      ),
    }))
  }

  const newChat = () => {
    inFlight.current?.abort()
    updateChat(owner, () => ({ turns: [], sessionId: null }))
  }

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    send(draft)
  }

  // Enter sends, Shift+Enter starts a new line, as in most chat boxes.
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      send(draft)
    }
  }

  return (
    <div className="ask-chat">
      <section className="panel ask-who" aria-label="Spaces the answer draws on">
        {options.length > 1 && (
          <HeaderSlot>
            <ScopePicker
              multiple
              label="Answer from"
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
          Your questions are saved to your own space
          {personal ? <span className="mono"> ({personal.scope_path})</span> : null} as
          memories. Answers are not saved as facts.
        </p>
      </section>

      <div className="chat-log" aria-live="polite">
        {turns.map((turn) => (
          <Fragment key={turn.id}>
            <p className="chat-question">{turn.question}</p>
            {turn.status === 'loading' && (
              <div className="panel ask-loading">
                <span className="ask-spinner" aria-hidden="true" />
                <output className="ask-loading-text">
                  <strong>Thinking…</strong>
                  <span className="ask-muted">
                    Looking through your spaces and writing an answer.
                  </span>
                </output>
                <button type="button" className="btn-secondary" onClick={cancel}>
                  Cancel
                </button>
              </div>
            )}
            {turn.status === 'cancelled' && <p className="empty">Cancelled.</p>}
            {turn.status === 'error' && (
              <div className="error" role="alert">
                <p className="ask-error-message">{turn.message}</p>
                {turn.hint && <p className="ask-error-hint">{turn.hint}</p>}
              </div>
            )}
            {turn.status === 'done' && (
              <ChatAnswer
                id={turn.id}
                question={turn.question}
                response={turn.response}
              />
            )}
          </Fragment>
        ))}
      </div>

      <form className="ask-form chat-form" onSubmit={onSubmit}>
        <label htmlFor={`${prefix}-message`} className="ask-label">
          Message
        </label>
        <textarea
          id={`${prefix}-message`}
          rows={2}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={
            turns.length
              ? 'Ask a follow-up…'
              : 'Which carrier ships to the Reno warehouse?'
          }
        />
        <div className="chat-actions">
          <button
            type="button"
            className="btn-secondary"
            onClick={newChat}
            disabled={!turns.length}
          >
            New chat
          </button>
          <button
            type="submit"
            className="btn"
            disabled={!draft.trim() || !areas.length || busy}
          >
            Send
          </button>
        </div>
      </form>
    </div>
  )
}

function hintFor(status: number | null): string | null {
  if (status === 404)
    return 'This chat has ended, for example after a server restart. Your next message will start a new chat.'
  if (status === 403) return 'One of the chosen spaces is not one you can read.'
  if (status === 503) return 'Agent Memory did not answer. Try again shortly.'
  return null
}

function ChatAnswer({
  id,
  question,
  response,
}: {
  id: string
  question: string
  response: ChatResponse
}) {
  const cited = new Map(response.citations.map((c) => [c.marker, c]))
  const anchor = (marker: string) => `${id}-${marker}`

  // A plain href would change the URL hash, which is the app's router.
  const jump = (event: MouseEvent<HTMLAnchorElement>, marker: string) => {
    event.preventDefault()
    const target = document.getElementById(anchor(marker))
    target?.scrollIntoView?.({ block: 'nearest' })
    target?.focus()
  }

  const marker = (label: string) =>
    cited.has(label) ? (
      <a
        className="chat-marker"
        href={`#${anchor(label)}`}
        aria-label={`Source ${label}`}
        onClick={(event) => jump(event, label)}
      >
        {label}
      </a>
    ) : (
      `[${label}]`
    )

  return (
    <article className="panel chat-answer" aria-label={`Answer to ${question}`}>
      <div className="chat-reply">
        <ReplyText text={response.reply} marker={marker} />
      </div>
      {response.citations.length ? (
        <ol className="chat-sources" aria-label="Sources">
          {response.citations.map((c) => (
            <li key={c.marker} id={anchor(c.marker)} tabIndex={-1}>
              <span className="chat-source-marker mono">{c.marker}</span>
              <span className="chat-source-body">
                <span>{c.snippet}</span>
                <span className="ask-muted chat-source-meta">{describe(c)}</span>
                <span className="ask-muted mono chat-source-meta">
                  match {formatScore(c.score)}
                </span>
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="ask-muted">No sources cited.</p>
      )}
    </article>
  )
}

/** "attribute", "chunk · Ops manual · 40%", "turn · earlier answer". */
function describe(c: ChatCitation): string {
  const bits = [c.kind]
  if (c.document_title) bits.push(c.document_title)
  if (c.position_percent !== null) bits.push(`${Math.round(c.position_percent)}%`)
  if (c.role === 'assistant') bits.push('earlier answer')
  return bits.join(' · ')
}
