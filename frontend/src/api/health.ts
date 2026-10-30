import { apiGet } from '@/api/client'

export interface Health {
  status: 'ok'
  version: string
  environment: string
}

export type AgentMemoryStatus = 'ok' | 'unavailable' | 'not_configured'

export interface Readiness {
  status: 'ok' | 'unavailable'
  agent_memory: AgentMemoryStatus
}

export const getHealth = (signal?: AbortSignal) =>
  apiGet<Health>('/api/v1/health', { signal })

// 503 still carries the readiness report, so it is an answer, not a failure.
export const getReadiness = (signal?: AbortSignal) =>
  apiGet<Readiness>('/api/v1/health/ready', { signal, acceptStatuses: [503] })
