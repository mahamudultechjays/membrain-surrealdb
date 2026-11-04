import { ApiError } from '@/api/client'
import type { LabApi, LabCounts, LabOutcome } from '@/api/lab'
import {
  MOCK_ADMINS,
  MOCK_REGISTERED,
  currentUser,
  delay,
  traceId,
} from '@/api/mock/backend'

/** Counts per scope (and '' for the whole context), changed by the mock jobs. */
const counts = new Map<string, LabCounts>()

const countsOf = (scope: string): LabCounts =>
  counts.get(scope) ?? {
    entities: 3,
    attributes: 9,
    relations: 2,
    by_source: { turn: 11 },
  }

function requireAdmin() {
  if (!MOCK_ADMINS.has(currentUser().email)) throw new ApiError(403, 'Admins only.')
}

function bump(scope: string, source: string, attributes: number, relations = 0) {
  const c = countsOf(scope)
  counts.set(scope, {
    entities: c.entities,
    attributes: c.attributes + attributes,
    relations: c.relations + relations,
    by_source: {
      ...c.by_source,
      [source]: (c.by_source[source] ?? 0) + attributes + relations,
    },
  })
}

/** A stand-in for the memory job endpoint: same checks, plausible numbers. */
export const mockLabApi: LabApi = {
  async scopes(signal) {
    requireAdmin()
    await delay(150, signal)
    return [...MOCK_REGISTERED].sort()
  },

  async run({ scope, action, query, dry_run = false, persist = false }, signal) {
    requireAdmin()
    if (scope === null && !(action === 'consolidate' && dry_run)) {
      throw new ApiError(422, 'the whole context only allows a consolidation preview')
    }
    await delay(600, signal)
    const key = scope ?? ''
    const before = countsOf(key)
    let outcome: LabOutcome
    if (action === 'consolidate') {
      if (!dry_run) bump(key, 'consolidation', 2)
      outcome = {
        summary: { created: 2, updated: 0, superseded: 0 },
        items: [
          'create · Acme Logistics · lead_time = 18 days (proof 2) · Repeated in two turns.',
          'create · Reno warehouse · returns_window = 60 days (proof 1) · Direct fact.',
        ],
        text: null,
        trace_ids: [traceId()],
      }
    } else if (action === 'elaborate') {
      if (!dry_run) bump(key, 'elaboration', 0, 1)
      outcome = {
        summary: { entities: before.entities, relations: 1 },
        items: ['organisation/acme_logistics serves location/reno_warehouse'],
        text: null,
        trace_ids: [traceId()],
      }
    } else {
      if (persist) bump(key, 'reflect', 1)
      outcome = {
        summary: { evidence: 2, saved: persist ? 1 : 0 },
        items: [`evidence: facts matching "${query ?? ''}"`],
        text: 'Acme Logistics is the only carrier on record, and its lead time has grown.',
        trace_ids: [traceId()],
      }
    }
    return {
      action,
      scope,
      before,
      after: countsOf(key),
      outcome,
      latency_ms: 600,
      ran_at: new Date().toISOString().replace(/\.\d+Z$/, '+00:00'),
    }
  },
}
