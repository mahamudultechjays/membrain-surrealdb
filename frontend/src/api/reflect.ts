import { apiPost } from '@/api/client'
import { USE_MOCK_API } from '@/api/config'
import { mockReflectApi } from '@/api/mock/reflect'

// Mirrors backend/app/schemas/reflect.py.

export interface ReflectRequest {
  question: string
  /** Narrows the readable scopes; empty reads them all. */
  scopes?: string[]
}

export interface ReflectResponse {
  /** The model's synthesis: its own conclusion, not a stored fact. */
  answer: string
  /** The stored memories it drew on, as Agent Memory quotes them. */
  evidence: string[]
  /** The scopes the answer could draw on. */
  scopes: string[]
  trace_id: string | null
}

export interface ReflectApi {
  ask(request: ReflectRequest, signal?: AbortSignal): Promise<ReflectResponse>
}

export const httpReflectApi: ReflectApi = {
  ask: (request, signal) =>
    apiPost<ReflectResponse>('/api/v1/ask/reflect', request, { signal }),
}

export const reflectApi: ReflectApi = USE_MOCK_API ? mockReflectApi : httpReflectApi
