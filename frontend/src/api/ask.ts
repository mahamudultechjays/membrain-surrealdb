import { apiGet } from '@/api/client'
import { USE_MOCK_API } from '@/api/config'
import { mockAskApi } from '@/api/mock/ask'

// Mirrors backend/app/schemas/ask.py on feat/capture-ak-scoping-api.

export type LayerName = 'org' | 'team' | 'personal'
/** Agent Memory's record kind for a recall hit. */
export type HitKind =
  'entity' | 'attribute' | 'action' | 'memory_chunk' | 'chunk' | 'section'

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
  /** Recall rank score for this query, not trust: /query exposes no per-hit trust. */
  score: number
}

export interface AskFact {
  fact: string
  source: FactSource
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
}

export interface AskResponse {
  q: string
  scopes: string[]
  answered_at: string
  layers: AskLayer[]
  metadata: AskMetadata
  trace_id: string | null
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
}

export interface AskApi {
  ask(request: AskRequest, signal?: AbortSignal): Promise<AskResponse>
}

export const httpAskApi: AskApi = {
  ask: ({ q, as_users = [], scopes = [], include_inferred = false }, signal) => {
    const params = new URLSearchParams({ q, include_inferred: String(include_inferred) })
    for (const email of as_users) params.append('as_user', email)
    for (const scope of scopes) params.append('scope', scope)
    return apiGet<AskResponse>(`/api/v1/ask?${params.toString()}`, { signal })
  },
}

export const askApi: AskApi = USE_MOCK_API ? mockAskApi : httpAskApi
