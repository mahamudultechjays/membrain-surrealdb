import { ApiError } from '@/api/client'
import type { Evidence, PromotionApi, PromotionStatus, ReviewItem } from '@/api/promotion'

// In-browser stand-in for /api/v1/promotion, matching the spec's sample design:
// two candidates, one active rule with an open flag, and a few decided items.

const said = (text: string, source: string, said_at: string) => ({
  text,
  source,
  said_at,
})
const row = (
  user: string,
  weights: number[],
  value: string,
  ...s: ReturnType<typeof said>[]
): Evidence => ({
  user,
  weights,
  value,
  said: s,
})

const base = {
  entity_type: 'organization',
  decided_by: null,
  decided_at: null,
  rule_id: null,
  people: 0,
  for_rows: [] as Evidence[],
  against_rows: [] as Evidence[],
}

function initial(): ReviewItem[] {
  return [
    {
      ...base, id: 1, kind: 'candidate', status: 'open', group_id: 1,
      label: 'Cobalt Ridge return window', entity: 'Cobalt Ridge', key: 'return_window',
      value: '30 days', score_when_listed: 3.5, team_score: 3.5, for_score: 4.5,
      against_score: 1, holders: ['member.a@spreetail.com', 'member.b@spreetail.com'],
      created_at: '2026-11-10T12:05:00+00:00', people: 5,
      values: [{ value: '30 days', team_score: 3.5 }, { value: '60 days', team_score: 1 }],
      for_rows: [
        row('member.a@spreetail.com', [1, 0.5], '30 days',
          said('Cobalt Ridge returns are 30 days', 'app', '2026-11-03T10:00:00+00:00'),
          said('Cobalt Ridge returns are 30 days', 'app', '2026-11-09T10:00:00+00:00')),
        row('member.b@spreetail.com', [1], '30 days',
          said('30-day window for Cobalt Ridge', 'chat', '2026-11-05T10:00:00+00:00')),
        row('member.c@spreetail.com', [1], '30 days',
          said('Customers get 30 days to return Cobalt Ridge items', 'chat', '2026-11-06T10:00:00+00:00')),
        row('member.e@spreetail.com', [1], '30 days',
          said('Cobalt Ridge: 30 day returns', 'chat', '2026-11-08T10:00:00+00:00')),
      ],
      against_rows: [
        row('member.d@spreetail.com', [1], '60 days',
          said('We give Cobalt Ridge 60 days', 'chat', '2026-11-07T10:00:00+00:00')),
      ],
    },
    {
      ...base, id: 4, kind: 'candidate', status: 'open', group_id: 3,
      label: 'Northwind lead time', entity: 'Northwind Outdoor', key: 'lead_time',
      value: '21 days', score_when_listed: 3, team_score: 3, for_score: 3, against_score: 0,
      holders: [], created_at: '2026-11-10T12:05:00+00:00', people: 3,
      values: [{ value: '21 days', team_score: 3 }],
    },
    {
      ...base, id: 2, kind: 'candidate', status: 'active', group_id: 2,
      label: 'Northwind free freight threshold', entity: 'Northwind Outdoor',
      key: 'free_freight_from', value: '$5,000', score_when_listed: 3, team_score: 2,
      for_score: 3, against_score: 1, holders: [],
      decided_by: 'admin@spreetail.com', decided_at: '2026-11-07T15:00:00+00:00',
      created_at: '2026-11-06T12:05:00+00:00', people: 4,
      values: [{ value: '$5,000', team_score: 2 }, { value: '$7,500', team_score: 1 }],
    },
    {
      ...base, id: 3, kind: 'flag', status: 'open', group_id: 2,
      label: 'Northwind free freight threshold', entity: 'Northwind Outdoor',
      key: 'free_freight_from', value: '$5,000', score_when_listed: 1, team_score: 2,
      for_score: 3, against_score: 1, holders: [], rule_id: 2,
      created_at: '2026-11-10T12:05:00+00:00', people: 4,
      values: [{ value: '$5,000', team_score: 2 }, { value: '$7,500', team_score: 1 }],
      against_rows: [
        row('member.f@spreetail.com', [1], '$7,500',
          said('Northwind free freight starts at $7,500', 'chat', '2026-11-08T10:00:00+00:00')),
      ],
    },
    {
      ...base, id: 5, kind: 'candidate', status: 'rejected', group_id: 4,
      label: 'Reno warehouse closing time', entity: 'Reno warehouse', key: 'closes_at',
      value: '6 pm', score_when_listed: 3, team_score: 3, for_score: 3, against_score: 0,
      holders: [], decided_by: 'admin@spreetail.com', decided_at: '2026-11-08T09:00:00+00:00',
      created_at: '2026-11-07T12:05:00+00:00', values: [{ value: '6 pm', team_score: 3 }],
    },
  ] // prettier-ignore
}

let items = initial()

const status = (): PromotionStatus => ({
  enabled: false,
  running: false,
  next_run_at: null,
  every_minutes: 240,
  team_scope: 'org/spreetail/team/common',
  model_configured: true,
  thresholds: { personal_rule_at: 1.75, candidate_at: 3, flag_at: 2, repeat_factor: 0.5 },
  last_run: {
    started_at: '2026-11-10T12:05:00+00:00', finished_at: '2026-11-10T12:06:10+00:00',
    listed: 42, new: 14, replaced: 1, grouped: 14, new_topics: 3, left: 0, opened: 1,
    dropped: 0, error: null,
  }, // prettier-ignore
  items: items.map((i) => ({ ...i })),
  groups: [
    { id: 1, label: 'Cobalt Ridge return window', values: [{ value: '30 days', team_score: 3.5 }, { value: '60 days', team_score: 1 }], people: 5 },
    { id: 2, label: 'Northwind free freight threshold', values: [{ value: '$5,000', team_score: 2 }, { value: '$7,500', team_score: 1 }], people: 4 },
    { id: 3, label: 'Northwind lead time', values: [{ value: '21 days', team_score: 3 }], people: 3 },
    { id: 4, label: 'Reno warehouse closing time', values: [{ value: '6 pm', team_score: 3 }], people: 3 },
  ], // prettier-ignore
})

function set(id: number, from: ReviewItem['status'][], to: ReviewItem['status']): void {
  const found = items.find((i) => i.id === id)
  if (!found || !from.includes(found.status)) {
    throw new ApiError(409, `Review item ${id} is ${found?.status ?? 'missing'}`)
  }
  found.status = to
  found.decided_by = 'admin@spreetail.com'
  found.decided_at = new Date().toISOString()
}

export const mockPromotionApi: PromotionApi = {
  status: async () => status(),
  run: async () => {},
  approve: async (id, edit) => {
    set(id, ['open'], 'active')
    const found = items.find((i) => i.id === id)
    if (found && edit) Object.assign(found, edit)
    return status()
  },
  reject: async (id) => {
    set(id, ['open'], 'rejected')
    return status()
  },
  keep: async (id) => {
    set(id, ['open'], 'kept')
    return status()
  },
  close: async (id) => {
    const found = items.find((i) => i.id === id)
    if (found?.kind === 'flag' && found.rule_id) {
      set(found.rule_id, ['active'], 'closed')
      set(id, ['open', 'kept'], 'closed')
    } else {
      set(id, ['active'], 'closed')
    }
    return status()
  },
}

/** For tests: back to the starting items. */
export function resetMockPromotion(): void {
  items = initial()
}
