import { apiGet } from '@/api/client'

export interface Health {
  status: 'ok'
  version: string
  environment: string
}

export interface Readiness {
  status: 'ok' | 'unavailable'
  database: 'ok' | 'unavailable'
}

export const getHealth = (signal?: AbortSignal) =>
  apiGet<Health>('/api/v1/health', signal)

export const getReadiness = (signal?: AbortSignal) =>
  apiGet<Readiness>('/api/v1/health/ready', signal)
