import { apiGet } from '@/api/client'
import { USE_MOCK_API } from '@/api/config'
import { mockBrainApi } from '@/api/mock/brain'

// Mirrors backend/app/schemas/brain.py.

/** Where a fact came from: kind "turn" (a captured input) or "elaboration" (inferred). */
export interface BrainSource {
  kind: string | null
  ref: string | null
  session_id: string | null
  trust: number | null
}

/** Fields Agent Memory keeps on facts and relations beyond the basics; null when unknown. */
interface BrainExtras {
  confidence?: number | null
  valid_from?: string | null
  valid_until?: string | null
  source?: BrainSource
}

export interface BrainFact extends BrainExtras {
  id: string
  /** The entity's type and key, e.g. "concept/tier_a_products". */
  entity_ref?: string
  importance?: number | null
  /** The fact this one replaced, and the fact that replaced this one. */
  supersedes?: string | null
  superseded_by?: string | null
  key: string
  value: string
  category: string
  /** The scopes this fact was written to. */
  scopes: string[]
  created_at: string
  /** True when a newer value replaced this one. */
  replaced: boolean
  /** Agent Memory's one-sentence version of the fact; null when it has none. */
  summary: string | null
  /** Descriptive tags such as "source=email"; empty when it has none. */
  labels: string[]
}

export interface BrainRelation extends BrainExtras {
  id: string
  subject_ref?: string
  label: string
  object_ref: string
  object_name: string
  category: string
  scopes: string[]
  created_at: string
  summary: string | null
  labels: string[]
}

export interface BrainEntity {
  ref: string
  name: string
  entity_type: string
  category: string
  scopes: string[]
  updated_at: string
  facts: BrainFact[]
  relations: BrainRelation[]
}

export interface BrainResponse {
  entities: BrainEntity[]
  /** Every scope the caller may filter by that holds something. */
  scopes: string[]
  total_facts: number
  total_relations: number
}

export interface BrainRequest {
  /** Narrow to these scopes; empty means everything the caller may read. */
  scopes?: string[]
  /** Count the paths below each chosen scope too. */
  subscopes?: boolean
}

export interface BrainApi {
  list(request: BrainRequest, signal?: AbortSignal): Promise<BrainResponse>
}

export const httpBrainApi: BrainApi = {
  list: ({ scopes = [], subscopes = false }, signal) => {
    const params = new URLSearchParams({ subscopes: String(subscopes) })
    for (const scope of scopes) params.append('scope', scope)
    return apiGet<BrainResponse>(`/api/v1/brain?${params.toString()}`, { signal })
  },
}

export const brainApi: BrainApi = USE_MOCK_API ? mockBrainApi : httpBrainApi
