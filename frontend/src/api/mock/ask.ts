import type {
  AskApi,
  AskLayer,
  AskMode,
  AskModeSource,
  AskRequest,
  AskResponse,
  FactProvenance,
} from '@/api/ask'
import { ApiError } from '@/api/client'
import { applyMode } from '@/api/mock/askModes'
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

/** The backend's ASK_TIE_MARGIN default. */
const TIE_MARGIN = 0.1
/** The backend's ASK_CONFLICT_MIN_SCORE default. */
const CONFLICT_MIN_SCORE = 0.4
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

/**
 * Like the backend: trust only for attribute hits at or above the floor. Org
 * and team facts read as structured upserts; personal ones as extracted from
 * chat, which Agent Memory trusts less.
 */
function trustOf(
  layer: MockLayerName,
  kind: string,
  matchScore: number,
): FactProvenance | null {
  if (kind !== 'attribute' || matchScore < CONFLICT_MIN_SCORE) return null
  const fromChat = layer === 'personal'
  return {
    trust: fromChat ? 0.5 : 0.95,
    confidence: fromChat ? 0.8 : 0.95,
    source_kind: fromChat ? 'turn' : 'upsert',
    created_at: '2026-11-09T08:32:50+00:00',
    valid_from: null,
    valid_until: null,
    superseded_by: null,
  }
}

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

interface Recalled {
  q: string
  scopes: string[]
  layers: AskLayer[]
  latency: number
  include_inferred: boolean
}

/** Every readable scope recalled once, like the backend's ask_flow.ask. */
async function recallAll(
  { q, as_users = [], scopes = [], include_inferred = false }: AskRequest,
  signal?: AbortSignal,
): Promise<Recalled> {
  {
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
            provenance: trustOf(layer.name, r.kind, 0.35 + s * 0.6),
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

    return {
      q,
      scopes: ordered.map((layer) => layer.path),
      layers,
      latency,
      include_inferred,
    }
  }
}

/** One mode's rules applied to a recall, without touching the recall itself. */
function answerIn(
  recalled: Recalled,
  usedMode: AskMode,
  modeSource: AskModeSource,
): AskResponse {
  const { q, latency, include_inferred } = recalled
  const layers = recalled.layers.map((layer) => ({ ...layer, facts: [...layer.facts] }))
  {
    const view = applyMode(usedMode, layers, TIE_MARGIN, CONFLICT_MIN_SCORE)
    for (const layer of layers)
      layer.facts = layer.facts.map((fact) => {
        const verdict = view.verdicts.get(fact.source.hit_id)
        return {
          ...fact,
          status: verdict?.status ?? null,
          reason: verdict?.reason ?? null,
          conflict_id: view.conflictOf.get(fact.source.hit_id) ?? null,
        }
      })

    const total = layers.reduce((n, layer) => n + layer.facts.length, 0)
    return {
      q,
      scopes: recalled.scopes,
      answered_at: new Date().toISOString().replace(/\.\d+Z$/, '+00:00'),
      layers,
      metadata: {
        total_facts: total,
        resolution_tier: total ? 'hybrid' : 'full_context',
        latency_ms: latency,
        include_inferred,
        trace_ids: recalled.scopes.map(() => traceId()),
        tie_margin: usedMode === 'best_match' ? TIE_MARGIN : null,
      },
      trace_id: traceId(),
      mode: usedMode,
      mode_source: modeSource,
      conflicts: view.conflicts,
    }
  }
}

export const mockAskApi: AskApi = {
  async ask(request, signal) {
    // Like the backend: a missing mode falls back to the configured default.
    const recalled = await recallAll(request, signal)
    return answerIn(
      recalled,
      request.mode ?? 'default',
      request.mode ? 'request' : 'config',
    )
  },
  async compare(request, signal) {
    const recalled = await recallAll(request, signal)
    return {
      q: request.q,
      best_match: answerIn(recalled, 'best_match', 'compare'),
      by_layer: answerIn(recalled, 'by_layer', 'compare'),
    }
  },
}
