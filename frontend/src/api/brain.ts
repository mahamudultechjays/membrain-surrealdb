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

/**
 * A memory chunk: the text of one captured turn, as memory stored it and
 * embeds for search. Facts name it in source.ref as "turn:<id>".
 */
export interface BrainChunk {
  id: string
  session_id: string
  /** "user" for captured input; chat sessions also hold "assistant" turns. */
  role: string
  text: string
  created_at: string
  /** Inferred from the facts taken from it: Agent Memory keeps no scope on turns. */
  scopes: string[]
  /** Ids of the facts and relations extracted from this text. */
  derived: string[]
}

export interface BrainResponse {
  entities: BrainEntity[]
  /** Every scope the caller may filter by that holds something. */
  scopes: string[]
  total_facts: number
  total_relations: number
  chunks: BrainChunk[]
  total_chunks: number
  /** Sessions whose chunks could not be read this time; 0 when all loaded. */
  chunks_missing: number
  actions: BrainAction[]
  unknowns: BrainUnknown[]
  /** True when replaced facts (read from each entity's history) are included. */
  replaced_loaded: boolean
  /** Entities whose history could not be read this time; 0 when all loaded. */
  replaced_missing: number
}

/** A dated event memory recorded: actor → verb → object. */
export interface BrainAction {
  id: string
  actor_ref: string
  actor_name: string
  verb: string
  object_ref: string | null
  /** The object entity's name, or the action's free-text object. */
  object_name: string | null
  summary: string | null
  category: string
  created_at: string
  occurred_at: string | null
  confidence: number | null
  /** Inferred from the facts taken from the same capture: actions carry no scope. */
  scopes: string[]
  source: BrainSource
}

/** Something memory could not settle: an unclear reference, or a contradiction. */
export interface BrainUnknown {
  id: string
  about: string
  reason: string
  resolved: boolean
  /** Whether memory thinks more input could settle it. */
  resolvable: boolean
  entity_ref: string | null
  entity_name: string | null
  key: string | null
  scopes: string[]
  labels: string[]
  created_at: string
}

export interface BrainRequest {
  /** Narrow to these scopes; empty means everything the caller may read. */
  scopes?: string[]
  /** Count the paths below each chosen scope too. */
  subscopes?: boolean
  /** Also read the facts newer values replaced (slower: one read per entity). */
  replaced?: boolean
}

export interface BrainApi {
  list(request: BrainRequest, signal?: AbortSignal): Promise<BrainResponse>
}

export const httpBrainApi: BrainApi = {
  list: ({ scopes = [], subscopes = false, replaced = false }, signal) => {
    const params = new URLSearchParams({
      subscopes: String(subscopes),
      replaced: String(replaced),
    })
    for (const scope of scopes) params.append('scope', scope)
    return apiGet<BrainResponse>(`/api/v1/brain?${params.toString()}`, { signal })
  },
}

export const brainApi: BrainApi = USE_MOCK_API ? mockBrainApi : httpBrainApi
