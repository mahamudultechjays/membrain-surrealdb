import { useSyncExternalStore } from 'react'
import type { LabAction, LabRun, LabRunRequest } from '@/api/lab'

export interface LabResult {
  request: LabRunRequest
  run: LabRun
}

export type LabResults = Partial<Record<LabAction, LabResult>>

const KEY = 'mb-lab-results'
const EMPTY: LabResults = {}
const listeners = new Set<() => void>()
let results: LabResults | null = null

/**
 * The last result of each job, kept outside the Admin page so it survives
 * leaving it, and in sessionStorage so a reload keeps it. Cleared on sign-out.
 */
function load(): LabResults {
  try {
    const raw = sessionStorage.getItem(KEY)
    if (!raw) return EMPTY
    // Jobs no longer preview; a preview kept from before would read as a real run.
    const saved = Object.entries(JSON.parse(raw) as LabResults).filter(
      ([, result]) => !result?.request.dry_run,
    )
    return Object.fromEntries(saved) as LabResults
  } catch {
    return EMPTY
  }
}

export function getLabResults(): LabResults {
  results ??= load()
  return results
}

function save(next: LabResults) {
  results = next
  try {
    if (Object.keys(next).length) sessionStorage.setItem(KEY, JSON.stringify(next))
    else sessionStorage.removeItem(KEY)
  } catch {
    // Storage full or blocked: results still live in memory for this visit.
  }
  listeners.forEach((notify) => notify())
}

/** Replaces that job's previous result. */
export function setLabResult(request: LabRunRequest, run: LabRun) {
  save({ ...getLabResults(), [request.action]: { request, run } })
}

export function clearLabResults() {
  save(EMPTY)
}

function subscribe(notify: () => void) {
  listeners.add(notify)
  return () => listeners.delete(notify)
}

export function useLabResults(): LabResults {
  return useSyncExternalStore(subscribe, getLabResults)
}
