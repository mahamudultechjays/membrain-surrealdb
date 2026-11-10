import { apiGet } from '@/api/client'
import { USE_MOCK_API } from '@/api/config'
import { mockAskApi } from '@/api/mock/ask'

// Mirrors backend/app/schemas/ask.py on feat/capture-ak-scoping-api.

export type LayerName = 'org' | 'team' | 'personal'

/**
 * How Search treats layers that disagree. Each is a separate backend path:
 * default lists every layer, best_match picks a value per conflict, by_layer
 * flags conflicts and picks nothing.
 */
export type AskMode = 'default' | 'best_match' | 'by_layer'
export const ASK_MODES: readonly AskMode[] = ['default', 'best_match', 'by_layer']
/**
 * Whether the mode came from the request, the backend's ASK_MODE_DEFAULT, or
 * /ask/compare asking for it alongside the other mode.
 */
export type AskModeSource = 'request' | 'config' | 'compare'
/** Agent Memory's record kind for a recall hit. */
export type HitKind =
  'entity' | 'attribute' | 'action' | 'memory_chunk' | 'chunk' | 'section'

/**
 * Where an attribute came from and how far Agent Memory trusts it, read from
 * the entity record (/query itself carries no trust).
 */
export interface FactProvenance {
  /** By how it was written: 0.95 upsert, 0.5 extracted from a chat turn, 0.35 consolidated. */
  trust: number | null
  /** How sure the writer was of this value. */
  confidence: number | null
  /** upsert, turn or consolidation. */
  source_kind: string | null
  created_at: string | null
  valid_from: string | null
  valid_until: string | null
  /** Set when a newer value replaced this one. */
  superseded_by: string | null
}

export interface FactSource {
  /** "document" for chunk and section hits, else "memory". */
  kind: 'document' | 'memory'
  hit_kind: HitKind | string
  hit_id: string
  /** Always null: recall hits carry no title or date. */
  title: string | null
  date: string | null
  /** The hit's own text, not a verified quote from the source. */
  text: string
  /** Recall rank score for this query. Not trust: see `provenance`. */
  score: number
  /** When the remembered event happened (memory chunks only). */
  occurred_at?: string | null
  /** Attribute hits that match the question; null otherwise or if the lookup failed. */
  provenance?: FactProvenance | null
}

export interface AskFact {
  fact: string
  source: FactSource
  /** Best match only: whether this fact's value was used or set aside. */
  status?: 'used' | 'set_aside' | null
  /** Best match only: why, e.g. "Scores within 0.10, so the broader Org layer wins". */
  reason?: string | null
  /** Best match and By layer: the conflict this fact belongs to, e.g. "c1". */
  conflict_id?: string | null
}

export interface ConflictValue {
  value: string
  layers: string[]
  /** Scope paths that hold this value. */
  areas: string[]
  hit_ids: string[]
  best_score: number
}

/** One point (entity and key) on which two or more scopes hold different values. */
export interface AskConflict {
  id: string
  entity: string
  key: string
  /** Highest score first. */
  values: ConflictValue[]
  /** Best match only: the hit whose value was chosen. */
  winner_hit_id: string | null
  /** Best match only: why that value won. */
  reason: string | null
}

export interface AskLayer {
  layer: LayerName
  /** The scope path read, e.g. org/spreetail, org/spreetail/team/ops. */
  area: string
  /** The user's name for a personal layer, else null. */
  owner: string | null
  facts: AskFact[]
  /** Set when this layer's recall failed; the other layers still answer. */
  error: string | null
}

export interface AskMetadata {
  total_facts: number
  /** Agent Memory's tiers, comma-joined, e.g. "direct,hybrid". */
  resolution_tier: string | null
  latency_ms: number
  /** Echoed back, but not applied: recall has no matching option. */
  include_inferred: boolean
  trace_ids: string[]
  /** Best match only: the score gap within which the broader layer wins. */
  tie_margin?: number | null
}

export interface AskResponse {
  q: string
  scopes: string[]
  answered_at: string
  layers: AskLayer[]
  metadata: AskMetadata
  trace_id: string | null
  mode: AskMode
  mode_source: AskModeSource
  /** Empty for the default mode. */
  conflicts: AskConflict[]
}

export interface AskRequest {
  q: string
  /**
   * Admins only: ask as these users (emails), e.g. two at once. Omitted means the
   * signed-in user, whose grants decide what is read.
   */
  as_users?: string[]
  /** Narrows the search to some of the readable scopes (403 if any is not readable). */
  scopes?: string[]
  include_inferred?: boolean
  /** Omitted means the backend's configured default mode. */
  mode?: AskMode
}

/** Best match and By layer for one question, both from the same recall. */
export interface AskCompareResponse {
  q: string
  best_match: AskResponse
  by_layer: AskResponse
}

export interface AskApi {
  ask(request: AskRequest, signal?: AbortSignal): Promise<AskResponse>
  /** Both compared modes in one request: every scope is recalled once, not twice. */
  compare(
    request: Omit<AskRequest, 'mode'>,
    signal?: AbortSignal,
  ): Promise<AskCompareResponse>
}

function askParams({
  q,
  as_users = [],
  scopes = [],
  include_inferred = false,
  mode,
}: AskRequest): string {
  const params = new URLSearchParams({ q, include_inferred: String(include_inferred) })
  for (const email of as_users) params.append('as_user', email)
  for (const scope of scopes) params.append('scope', scope)
  if (mode) params.set('mode', mode)
  return params.toString()
}

export const httpAskApi: AskApi = {
  ask: (request, signal) =>
    apiGet<AskResponse>(`/api/v1/ask?${askParams(request)}`, { signal }),
  compare: (request, signal) =>
    apiGet<AskCompareResponse>(`/api/v1/ask/compare?${askParams(request)}`, { signal }),
}

export const askApi: AskApi = USE_MOCK_API ? mockAskApi : httpAskApi
