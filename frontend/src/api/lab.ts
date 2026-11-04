import { apiGet, apiPost } from '@/api/client'
import { USE_MOCK_API } from '@/api/config'
import { mockLabApi } from '@/api/mock/lab'

// Mirrors backend/app/schemas/lab.py. Every call needs an admin session.

export type LabAction = 'consolidate' | 'elaborate' | 'reflect'

export interface LabCounts {
  entities: number
  attributes: number
  relations: number
  /** Attributes and relations by origin: turn, elaboration, consolidation, reflect, ... */
  by_source: Record<string, number>
}

export interface LabOutcome {
  summary: Record<string, number>
  items: string[]
  text: string | null
  trace_ids: string[]
}

export interface LabRun {
  action: LabAction
  /** Null for the whole context. */
  scope: string | null
  before: LabCounts
  after: LabCounts
  outcome: LabOutcome
  latency_ms: number
  ran_at: string
}

export interface LabRunRequest {
  /** Null: the whole context, allowed only as a consolidation preview. */
  scope: string | null
  action: LabAction
  /** Reflect: the synthesis question. */
  query?: string
  /** Consolidate / elaborate: preview only, nothing saved. */
  dry_run?: boolean
  /** Reflect: save the insights as new facts. */
  persist?: boolean
}

export interface LabApi {
  /** Registered scopes under the org scope. */
  scopes(signal?: AbortSignal): Promise<string[]>
  run(request: LabRunRequest, signal?: AbortSignal): Promise<LabRun>
}

export const httpLabApi: LabApi = {
  scopes: async (signal) =>
    (await apiGet<{ scopes: string[] }>('/api/v1/admin/scopes', { signal })).scopes,
  run: (request, signal) =>
    apiPost<LabRun>('/api/v1/admin/lab/runs', request, { signal }),
}

export const labApi: LabApi = USE_MOCK_API ? mockLabApi : httpLabApi
