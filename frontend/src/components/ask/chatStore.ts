import { useSyncExternalStore } from 'react'
import type { ChatResponse } from '@/api/chat'

/** One question and what became of it. */
export type Turn = {
  id: string
  question: string
} & (
  | { status: 'loading' }
  | { status: 'cancelled' }
  | { status: 'done'; response: ChatResponse }
  | { status: 'error'; message: string; hint: string | null }
)

export interface ChatState {
  turns: Turn[]
  /** Agent Memory's session, sent with follow-ups; null starts a new one. */
  sessionId: string | null
}

const EMPTY: ChatState = { turns: [], sessionId: null }
const PREFIX = 'mb-chat:'

/**
 * Each person's chat, kept outside the chat screen so it survives leaving the
 * page, and in sessionStorage so it survives a reload of this browser tab.
 * Sign-out clears it (clearChats); closing the tab drops it.
 */
const chats = new Map<string, ChatState>()
const listeners = new Set<() => void>()

function load(owner: string): ChatState {
  try {
    const raw = sessionStorage.getItem(PREFIX + owner)
    if (!raw) return EMPTY
    const saved = JSON.parse(raw) as ChatState
    // A request in flight when the page went away will never answer.
    const turns = saved.turns.map((t): Turn =>
      t.status === 'loading'
        ? { id: t.id, question: t.question, status: 'cancelled' }
        : t,
    )
    return { turns, sessionId: saved.sessionId ?? null }
  } catch {
    // Blocked or corrupt storage: start afresh rather than fail the page.
    return EMPTY
  }
}

export function getChat(owner: string): ChatState {
  let state = chats.get(owner)
  if (!state) {
    state = load(owner)
    chats.set(owner, state)
  }
  return state
}

export function updateChat(owner: string, change: (state: ChatState) => ChatState) {
  const next = change(getChat(owner))
  chats.set(owner, next)
  try {
    sessionStorage.setItem(PREFIX + owner, JSON.stringify(next))
  } catch {
    // Storage full or blocked: the chat still lives in memory for this visit.
  }
  listeners.forEach((notify) => notify())
}

/** Forgets every conversation, in memory and in storage. Called on sign-out. */
export function clearChats() {
  chats.clear()
  try {
    for (const key of Object.keys(sessionStorage)) {
      if (key.startsWith(PREFIX)) sessionStorage.removeItem(key)
    }
  } catch {
    // Nothing stored, or storage blocked.
  }
  listeners.forEach((notify) => notify())
}

function subscribe(notify: () => void) {
  listeners.add(notify)
  return () => listeners.delete(notify)
}

/** The owner's chat, re-rendering whenever it changes. */
export function useChat(owner: string): ChatState {
  return useSyncExternalStore(subscribe, () => getChat(owner))
}
