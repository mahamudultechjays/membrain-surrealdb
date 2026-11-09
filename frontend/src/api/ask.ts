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

export interface AskMetadata {
  total_facts: number
  /** How Agent Memory resolved the recall, e.g. "hybrid" or "escalated". */
  resolution_tier: string | null
  latency_ms: number
  /** Echoed back, but not applied: recall has no matching option. */
  include_inferred: boolean
  trace_ids: string[]
}

export interface AskResponse {
  q: string
  /** The scopes the one recall read, org first, then team, then personal. */
  scopes: string[]
  answered_at: string
  /** Agent Memory's ranking across all those scopes. Hits carry no scope. */
  facts: AskFact[]
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
