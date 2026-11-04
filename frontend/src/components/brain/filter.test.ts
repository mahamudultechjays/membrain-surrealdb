import type { BrainEntity } from '@/api/brain'
import { NO_FILTERS, applyFilters, parseDate, toRows } from '@/components/brain/filter'

const NOW = Date.parse('2026-11-03T12:00:00Z')

const fact = (
  id: string,
  key: string,
  at: string,
  extra: Partial<BrainEntity['facts'][0]> = {},
) => ({
  id,
  key,
  value: `${key} value`,
  category: 'context',
  scopes: ['org/spreetail/user/arun_das'],
  created_at: at,
  replaced: false,
  summary: null,
  labels: [],
  ...extra,
})

const ENTITIES: BrainEntity[] = [
  {
    ref: 'concept/tier_a',
    name: 'Tier A products',
    entity_type: 'concept',
    category: 'knowledge',
    scopes: ['org/spreetail/user/arun_das'],
    updated_at: '2026-11-03T10:00:00.123456789+00:00',
    facts: [
      fact('f1', 'pre_build_weeks', '2026-11-03T10:00:00.123456789+00:00'),
      fact('f2', 'old_pre_build_weeks', '2026-10-01T10:00:00+00:00', { replaced: true }),
    ],
    relations: [],
  },
  {
    ref: 'organisation/acme',
    name: 'Acme Logistics',
    entity_type: 'organisation',
    category: 'knowledge',
    scopes: ['org/spreetail'],
    updated_at: '2026-10-21T09:00:00+00:00',
    facts: [
      fact('f3', 'lead_time', '2026-10-20T09:00:00+00:00', { category: 'knowledge' }),
    ],
    relations: [
      {
        id: 'r1',
        label: 'ships_to',
        object_ref: 'place/reno',
        object_name: 'Reno warehouse',
        category: 'context',
        scopes: ['org/spreetail'],
        created_at: '2026-10-21T09:00:00+00:00',
        summary: 'Acme ships to the Reno warehouse every week',
        labels: ['source=email'],
      },
    ],
  },
]

const ROWS = toRows(ENTITIES)
const keys = (rows: ReturnType<typeof toRows>) => rows.map((r) => r.key)

describe('brain filters', () => {
  it('reads Agent Memory nanosecond timestamps', () => {
    expect(parseDate('2026-11-03T10:00:00.123456789+00:00')).toBe(
      Date.parse('2026-11-03T10:00:00.123Z'),
    )
    expect(parseDate('not a date')).toBe(0)
  })

  it('turns every fact and relation into its own row', () => {
    expect(ROWS.map((r) => [r.kind, r.entity, r.key, r.value])).toEqual([
      ['fact', 'Tier A products', 'pre_build_weeks', 'pre_build_weeks value'],
      ['fact', 'Tier A products', 'old_pre_build_weeks', 'old_pre_build_weeks value'],
      ['fact', 'Acme Logistics', 'lead_time', 'lead_time value'],
      ['relation', 'Acme Logistics', 'ships_to', 'Reno warehouse'],
    ])
  })

  it('hides replaced values unless asked for, latest first', () => {
    expect(keys(applyFilters(ROWS, NO_FILTERS, NOW))).toEqual([
      'pre_build_weeks',
      'ships_to',
      'lead_time',
    ])
    expect(applyFilters(ROWS, { ...NO_FILTERS, showReplaced: true }, NOW)).toHaveLength(4)
  })

  it('searches the entity, the fact and the value', () => {
    expect(keys(applyFilters(ROWS, { ...NO_FILTERS, query: 'acme' }, NOW))).toEqual([
      'ships_to',
      'lead_time',
    ])
    expect(keys(applyFilters(ROWS, { ...NO_FILTERS, query: 'reno' }, NOW))).toEqual([
      'ships_to',
    ])
    // The summary is searched too.
    expect(keys(applyFilters(ROWS, { ...NO_FILTERS, query: 'every week' }, NOW))).toEqual(
      ['ships_to'],
    )
  })

  it('filters by kind, entity type, category and saved date', () => {
    expect(keys(applyFilters(ROWS, { ...NO_FILTERS, kind: 'relation' }, NOW))).toEqual([
      'ships_to',
    ])
    expect(
      keys(applyFilters(ROWS, { ...NO_FILTERS, type: 'organisation' }, NOW)),
    ).toEqual(['ships_to', 'lead_time'])
    expect(
      keys(applyFilters(ROWS, { ...NO_FILTERS, category: 'knowledge' }, NOW)),
    ).toEqual(['lead_time'])
    expect(keys(applyFilters(ROWS, { ...NO_FILTERS, since: '7d' }, NOW))).toEqual([
      'pre_build_weeks',
    ])
  })

  it('sorts oldest first, by entity and by fact', () => {
    expect(keys(applyFilters(ROWS, { ...NO_FILTERS, sort: 'oldest' }, NOW))).toEqual([
      'lead_time',
      'ships_to',
      'pre_build_weeks',
    ])
    expect(
      applyFilters(ROWS, { ...NO_FILTERS, sort: 'entity' }, NOW).map((r) => r.entity),
    ).toEqual(['Acme Logistics', 'Acme Logistics', 'Tier A products'])
    expect(keys(applyFilters(ROWS, { ...NO_FILTERS, sort: 'fact' }, NOW))).toEqual([
      'lead_time',
      'pre_build_weeks',
      'ships_to',
    ])
  })
})
