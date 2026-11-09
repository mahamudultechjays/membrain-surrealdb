import { apiGet, apiPost, apiPut } from '@/api/client'

// Mirrors backend/app/schemas/vct_tags.py, schemas/onboarding.py (the map) and
// schemas/tagger.py. Facts stay in Agent Memory; these are only their tags.

export type TagKind = 'node' | 'goal'

export interface TagRef {
  kind: TagKind
  id: string
  name: string
  section_id: string
  section: string | null
  /** A node's domain; goals belong to sections only. */
  domain_id?: string | null
  domain?: string | null
  /** "auto" from the tagger, "user" once a person set or confirmed it. */
  source: 'auto' | 'user'
  rank: number
}

export interface FactTags {
  node: TagRef | null
  goal: TagRef | null
}

export interface FactTagDetail {
  fact_id: string
  scope: string
  /** False when the tagger judged it not business; adding a tag makes it business. */
  business: boolean
  tagged_at: string | null
  reviewed_at: string | null
  reviewed_by: string | null
  /** A not-business fact's best matches, for "Tag it". */
  guess_nodes: TagRef[]
  guess_goals: TagRef[]
  /** Rank order: the first is active, the rest are the tagger's alternatives. */
  nodes: TagRef[]
  goals: TagRef[]
}

export type TagAction =
  'change' | 'remove' | 'accept' | 'confirm' | 'not_business' | 'keep' | 'tag_guesses'

export interface VctNode {
  id: string
  name: string
  description: string
  domain_id: string
  section_id: string
}

export interface VctGoal {
  id: string
  name: string
  description: string
  /** The goal's share of EBITDA. */
  weight: number
}

export interface VctMap {
  topology_version: string
  domains: { id: string; name: string; nodes: VctNode[] }[]
  sections: { id: string; label: string; ebitda_weight: number; goals: VctGoal[] }[]
}

export interface VctCoverage {
  scopes: string[]
  tagged_facts: number
  without_goal: number
  not_business: number
  nodes: { id: string; facts: number }[]
  goals: { id: string; facts: number }[]
  /** One per domain x section that holds map nodes; facts 0 is a gap. */
  cells: { domain_id: string; section_id: string; nodes: number; facts: number }[]
}

export interface TaggerRun {
  started_at: string
  finished_at: string | null
  scopes: string[]
  listed: number
  new: number
  tagged: number
  not_business: number
  carried: number
  failed: number
  capped: boolean
  error: string | null
}

export interface TaggerStatus {
  enabled: boolean
  version: string
  scopes: string[]
  interval_hours: number
  running: boolean
  next_run_at: string | null
  current: TaggerRun | null
  last: TaggerRun | null
  tagged_facts: number
  not_business: number
  stats: {
    days: number
    edits: number
    corrections: number
    correction_rate: number | null
    confusions: { old: string; new: string | null; times: number }[]
  } | null
}

export interface OnboardingPreview {
  clauses: { clause: string; candidates: VctNode[] }[]
  /** The first candidate of each clause, once each: pre-tick these. */
  suggested: string[]
  domains: { id: string; name: string }[]
}

export interface OnboardingStatus {
  email: string
  onboarded: boolean
  primary_work: string | null
  nodes: (VctNode & {
    rank: number
    is_primary: boolean
    confirmed_by: 'user' | 'admin'
  })[]
  domains: { id: string; name: string }[]
}

export interface VctApi {
  map(signal?: AbortSignal): Promise<VctMap>
  factTags(factId: string, signal?: AbortSignal): Promise<FactTagDetail>
  /** change/remove/accept need a kind; the review actions do not. */
  editTag(
    factId: string,
    edit: { kind?: TagKind; action: TagAction; tag?: string },
  ): Promise<FactTagDetail>
  /** Review many facts at once, e.g. "Confirm all" on a group. */
  reviewFacts(
    factIds: string[],
    action: 'confirm' | 'keep',
  ): Promise<{ done: string[]; skipped: string[] }>
  coverage(signal?: AbortSignal): Promise<VctCoverage>
  tagger(signal?: AbortSignal): Promise<TaggerStatus>
  /** `retag` re-tags every fact in the tagged spaces; a person's tags stay. */
  runTagger(retag?: boolean): Promise<TaggerStatus>
  /** Match a description of someone's work to VCT nodes; nothing is saved. */
  previewOnboarding(primaryWork: string): Promise<OnboardingPreview>
  /** Admin: a user's onboarding, and replacing their nodes. */
  userOnboarding(email: string, signal?: AbortSignal): Promise<OnboardingStatus>
  setUserNodes(email: string, nodeIds: string[]): Promise<OnboardingStatus>
}

const fact = (id: string) => `/api/v1/facts/${encodeURIComponent(id)}/tags`

export const vctApi: VctApi = {
  map: (signal) => apiGet<VctMap>('/api/v1/vct/map', { signal }),
  factTags: (factId, signal) => apiGet<FactTagDetail>(fact(factId), { signal }),
  editTag: (factId, edit) => apiPut<FactTagDetail>(fact(factId), edit),
  reviewFacts: (factIds, action) =>
    apiPost<{ done: string[]; skipped: string[] }>('/api/v1/facts/review', {
      fact_ids: factIds,
      action,
    }),
  coverage: (signal) => apiGet<VctCoverage>('/api/v1/vct/coverage', { signal }),
  tagger: (signal) => apiGet<TaggerStatus>('/api/v1/admin/vct/tagger', { signal }),
  runTagger: (retag = false) =>
    apiPost<TaggerStatus>(`/api/v1/admin/vct/tagger/run${retag ? '?retag=true' : ''}`),
  previewOnboarding: (primaryWork) =>
    apiPost<OnboardingPreview>('/api/v1/onboarding/preview', {
      primary_work: primaryWork,
    }),
  userOnboarding: (email, signal) =>
    apiGet<OnboardingStatus>(
      `/api/v1/admin/users/${encodeURIComponent(email)}/onboarding`,
      {
        signal,
      },
    ),
  setUserNodes: (email, nodeIds) =>
    apiPut<OnboardingStatus>(`/api/v1/admin/users/${encodeURIComponent(email)}/vct`, {
      node_ids: nodeIds,
      primary_node_id: nodeIds[0] ?? null,
    }),
}

/** The active tags of a fact, from the editor's full detail. */
export function activeTags(detail: FactTagDetail): FactTags | null {
  const node = detail.nodes[0] ?? null
  const goal = detail.goals[0] ?? null
  return node || goal ? { node, goal } : null
}
