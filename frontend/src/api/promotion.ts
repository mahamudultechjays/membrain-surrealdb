import { apiGet, apiPost } from '@/api/client'
import { USE_MOCK_API } from '@/api/config'
import { mockPromotionApi } from '@/api/mock/promotion'

// Mirrors backend/app/schemas/promotion.py. Org admins and team admins only.

export type ReviewKind = 'candidate' | 'flag'
export type ReviewStatus = 'open' | 'active' | 'closed' | 'rejected' | 'dropped' | 'kept'

export interface PromotionRun {
  started_at: string
  finished_at: string | null
  listed: number
  new: number
  replaced: number
  grouped: number
  new_topics: number
  left: number
  opened: number
  dropped: number
  error: string | null
}

export interface ValueChip {
  value: string
  team_score: number
}

export interface Said {
  text: string
  /** chat (Claude plugin or Chat) or app (Capture). */
  source: string
  said_at: string
}

export interface Evidence {
  user: string
  weights: number[]
  /** What they hold: the value, or "not <value>". */
  value: string
  said: Said[]
}

export interface Group {
  id: number
  label: string
  values: ValueChip[]
  people: number
}

export interface ReviewItem {
  id: number
  kind: ReviewKind
  status: ReviewStatus
  group_id: number
  label: string
  entity_type: string
  entity: string
  key: string
  value: string
  score_when_listed: number
  /** Now, from the latest statements. */
  team_score: number
  for_score: number
  against_score: number
  holders: string[]
  decided_by: string | null
  decided_at: string | null
  /** For a flag: the rule it questions. */
  rule_id: number | null
  created_at: string | null
  /** Every value said in this topic, highest score first. */
  values: ValueChip[]
  people: number
  for_rows: Evidence[]
  against_rows: Evidence[]
}

export interface PromotionStatus {
  enabled: boolean
  running: boolean
  next_run_at: string | null
  every_minutes: number
  team_scope: string
  model_configured: boolean
  thresholds: {
    personal_rule_at: number
    candidate_at: number
    flag_at: number
    repeat_factor: number
  }
  last_run: PromotionRun | null
  items: ReviewItem[]
  groups: Group[]
}

export interface RuleEdit {
  label: string
  entity_type: string
  entity: string
  key: string
  value: string
}

export interface PromotionApi {
  status(signal?: AbortSignal): Promise<PromotionStatus>
  run(): Promise<void>
  approve(id: number, edit?: RuleEdit): Promise<PromotionStatus>
  reject(id: number): Promise<PromotionStatus>
  keep(id: number): Promise<PromotionStatus>
  close(id: number): Promise<PromotionStatus>
}

const item = (id: number, action: string) => `/api/v1/promotion/items/${id}/${action}`

export const httpPromotionApi: PromotionApi = {
  status: (signal) => apiGet<PromotionStatus>('/api/v1/promotion', { signal }),
  run: async () => {
    await apiPost('/api/v1/promotion/run')
  },
  approve: (id, edit) => apiPost<PromotionStatus>(item(id, 'approve'), edit),
  reject: (id) => apiPost<PromotionStatus>(item(id, 'reject')),
  keep: (id) => apiPost<PromotionStatus>(item(id, 'keep')),
  close: (id) => apiPost<PromotionStatus>(item(id, 'close')),
}

export const promotionApi: PromotionApi = USE_MOCK_API
  ? mockPromotionApi
  : httpPromotionApi
