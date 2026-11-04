import { useSyncExternalStore } from 'react'
import type { ReflectResponse } from '@/api/reflect'

/** One reflection question and what became of it. */
export type Reflection = {
  id: string
  question: string
} & (
  | { status: 'loading' }
  | { status: 'cancelled' }
  | { status: 'done'; response: ReflectResponse }
  | { status: 'error'; message: string }
)

const PREFIX = 'mb-reflect:'
const EMPTY: Reflection[] = []
const lists = new Map<string, Reflection[]>()
const listeners = new Set<() => void>()

/**
 * Each person's reflections, kept outside the page so they survive leaving it,
 * and in sessionStorage so a reload keeps them. Sign-out clears them.
 */
function load(owner: string): Reflection[] {
  try {
    const raw = sessionStorage.getItem(PREFIX + owner)
    if (!raw) return EMPTY
    // A request in flight when the page went away will never answer.
    return (JSON.parse(raw) as Reflection[]).map((r): Reflection =>
      r.status === 'loading'
        ? { id: r.id, question: r.question, status: 'cancelled' }
        : r,
    )
  } catch {
    return EMPTY
  }
}

export function getReflections(owner: string): Reflection[] {
  let list = lists.get(owner)
  if (!list) {
    list = load(owner)
    lists.set(owner, list)
  }
  return list
}

export function updateReflections(
  owner: string,
  change: (list: Reflection[]) => Reflection[],
) {
  const next = change(getReflections(owner))
  lists.set(owner, next)
  try {
    if (next.length) sessionStorage.setItem(PREFIX + owner, JSON.stringify(next))
    else sessionStorage.removeItem(PREFIX + owner)
  } catch {
    // Storage full or blocked: the list still lives in memory for this visit.
  }
  listeners.forEach((notify) => notify())
}

/** Forgets everyone's reflections, in memory and in storage. Called on sign-out. */
export function clearReflections() {
  lists.clear()
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

export function useReflections(owner: string): Reflection[] {
  return useSyncExternalStore(subscribe, () => getReflections(owner))
}
