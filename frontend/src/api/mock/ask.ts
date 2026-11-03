import type { AskApi, AskLayer } from '@/api/ask'
import { ApiError } from '@/api/client'
import {
  MOCK_ADMINS,
  currentUser,
  delay,
  records,
  traceId,
  userByEmail,
  type MockGrant,
  type MockLayerName,
} from '@/api/mock/backend'

const LAYER_LIMITS = { org: 20, team: 10, personal: 10 } as const
const LAYER_ORDER = { org: 0, team: 1, personal: 2 } as const
const STOP_WORDS = new Set([
  'what',
  'do',
  'we',
  'know',
  'about',
  'the',
  'is',
  'are',
  'a',
  'an',
  'of',
  'for',
  'our',
  'my',
  'how',
  'who',
  'when',
  'does',
  'did',
  'to',
  'in',
])

/** Word overlap between question and record, as a 0–1 score. */
function score(question: string[], text: string): number {
  const words = new Set(
    text
      .toLowerCase()
      .split(/[^a-z0-9%]+/)
      .filter(Boolean),
  )
  const hits = question.filter(
    (w) => words.has(w) || [...words].some((x) => x.startsWith(w)),
  )
  return question.length ? hits.length / question.length : 0
}

export const mockAskApi: AskApi = {
  async ask({ q, as_users = [], scopes = [], include_inferred = false }, signal) {
    const me = currentUser()
    if (as_users.length && !MOCK_ADMINS.has(me.email)) {
      throw new ApiError(403, 'Only admins can ask as other users.')
    }
    const users = as_users.length
      ? as_users.map((email) => {
          const user = userByEmail(email)
          if (!user) throw new ApiError(404, 'No readable scopes for that user.')
          return user
        })
      : [me]

    // Every granted scope once, org first, then team, then personal.
    const reads = new Map<
      string,
      { name: MockLayerName; path: string; owner: string | null }
    >()
    for (const user of users)
      for (const grant of user.grants as MockGrant[])
        if (!reads.has(grant.scope_path))
          reads.set(grant.scope_path, {
            name: grant.layer,
            path: grant.scope_path,
            owner: grant.layer === 'personal' ? user.name : null,
          })
    // Like the backend's `scope` filter: only readable scopes may be asked for.
    if (scopes.length) {
      const missing = scopes.filter((s) => !reads.has(s))
      if (missing.length) throw new ApiError(403, `Not readable: ${missing.join(', ')}`)
      for (const path of [...reads.keys()]) if (!scopes.includes(path)) reads.delete(path)
    }
    const ordered = [...reads.values()].sort(
      (a, b) => LAYER_ORDER[a.name] - LAYER_ORDER[b.name] || a.path.localeCompare(b.path),
    )

    // Recall is slow: the real backend took about 10 s in its first live test.
    const latency = 1800 + Math.round(Math.random() * 1200)
    await delay(latency, signal)

    const words = q
      .toLowerCase()
      .split(/[^a-z0-9%]+/)
      .filter((w) => w.length > 1 && !STOP_WORDS.has(w))
    const layers: AskLayer[] = ordered.map((layer) => {
      const facts = records
        .filter((r) => r.area === layer.path)
        .map((r) => ({ r, s: score(words, r.text) }))
        .filter(({ s }) => s > 0)
        .sort((a, b) => b.s - a.s)
        .slice(0, LAYER_LIMITS[layer.name])
        .map(({ r, s }) => ({
          fact: r.text,
          source: {
            kind: r.kind === 'chunk' ? ('document' as const) : ('memory' as const),
            hit_kind: r.kind,
            hit_id: r.id,
            title: null,
            date: null,
            text: r.text,
            score: Math.round((0.35 + s * 0.6) * 1000) / 1000,
          },
        }))
      return {
        layer: layer.name,
        area: layer.path,
        owner: layer.owner,
        facts,
        error: null,
      }
    })

    const total = layers.reduce((n, layer) => n + layer.facts.length, 0)
    return {
      q,
      scopes: ordered.map((layer) => layer.path),
      answered_at: new Date().toISOString().replace(/\.\d+Z$/, '+00:00'),
      layers,
      metadata: {
        total_facts: total,
        resolution_tier: total ? 'hybrid' : 'full_context',
        latency_ms: latency,
        include_inferred,
        trace_ids: ordered.map(() => traceId()),
      },
      trace_id: traceId(),
    }
  },
}
