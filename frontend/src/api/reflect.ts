import type { LayerName } from '@/api/ask'
import { apiPost } from '@/api/client'
import { USE_MOCK_API } from '@/api/config'
import { mockReflectApi } from '@/api/mock/reflect'

// Mirrors backend/app/schemas/reflect.py.

export interface ReflectRequest {
  question: string
  /** Narrows the readable scopes; empty reads them all. */
  scopes?: string[]
}

/**
 * applies: the highest layer whose reflection drew on evidence.
 * overridden: a lower layer that also had evidence. empty: no evidence.
 * failed: that layer's reflection call failed.
 */
export type ReflectLayerStatus = 'applies' | 'overridden' | 'empty' | 'failed'

export interface ReflectLayer {
  layer: LayerName
  scope: string
  status: ReflectLayerStatus
  /** The model's synthesis from this scope alone; null when it failed. */
  answer: string | null
  /** The stored memories it drew on, as Agent Memory quotes them. */
  evidence: string[]
  error: string | null
  trace_id: string | null
}

export interface ReflectResponse {
  /** One per scope, org first, then team, then personal. */
  layers: ReflectLayer[]
  /** The scope whose reflection applies, or null when no layer had evidence. */
  applies: string | null
  scopes: string[]
}

export interface ReflectApi {
  ask(request: ReflectRequest, signal?: AbortSignal): Promise<ReflectResponse>
}

export const httpReflectApi: ReflectApi = {
  ask: (request, signal) =>
    apiPost<ReflectResponse>('/api/v1/ask/reflect', request, { signal }),
}

export const reflectApi: ReflectApi = USE_MOCK_API ? mockReflectApi : httpReflectApi
