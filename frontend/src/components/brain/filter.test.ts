import type { BrainChunk, BrainEntity } from '@/api/brain'
import {
  NO_FILTERS,
  isRecord,
  applyFilters,
  countKinds,
  facets,
  parseDate,
  toRows,
  type BrainRow,
  type Origin,
} from '@/components/brain/filter'

const NOW = Date.parse('2026-11-03T12:00:00Z')
const SOURCE = { kind: 'turn', ref: null, session_id: 's1', trust: 0.5 }

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
/** A record's key, or a chunk's text: one label per row. */
const keys = (rows: readonly BrainRow[]) =>
  rows.map((r) => (isRecord(r) ? r.key : r.kind === 'chunk' ? r.text : r.id))
const records = (rows: readonly BrainRow[]) => rows.filter(isRecord)

const CHUNKS: BrainChunk[] = [
  {
    id: 't1',
    session_id: 's1',
    role: 'user',
    text: 'Acme ships to Reno; lead time is 6 days.',
    created_at: '2026-10-20T08:59:00+00:00',
    scopes: ['org/spreetail'],
    derived: ['f3', 'r1', 'gone'],
  },
  {
    id: 't2',
    session_id: 's1',
    role: 'assistant',
    text: 'Noted.',
    created_at: '2026-11-03T11:00:00+00:00',
    scopes: ['org/spreetail'],
    derived: [],
  },
]

/** The same entities, with f3 and r1 taken from chunk t1. */
const WITH_CHUNKS = toRows(
  ENTITIES.map((entity) => ({
    ...entity,
    facts: entity.facts.map((f) =>
      f.id === 'f3' ? { ...f, source: { ...SOURCE, ref: 'turn:t1' } } : f,
    ),
    relations: entity.relations.map((r) => ({
      ...r,
      source: { ...SOURCE, ref: 'turn:t1' },
    })),
  })),
  CHUNKS,
)

describe('brain filters', () => {
  it('reads Agent Memory nanosecond timestamps', () => {
    expect(parseDate('2026-11-03T10:00:00.123456789+00:00')).toBe(
      Date.parse('2026-11-03T10:00:00.123Z'),
    )
    expect(parseDate('not a date')).toBe(0)
  })

  it('turns every fact and relation into its own row', () => {
    expect(records(ROWS).map((r) => [r.kind, r.entity, r.key, r.value])).toEqual([
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
      records(applyFilters(ROWS, { ...NO_FILTERS, sort: 'entity' }, NOW)).map(
        (r) => r.entity,
      ),
    ).toEqual(['Acme Logistics', 'Acme Logistics', 'Tier A products'])
    expect(keys(applyFilters(ROWS, { ...NO_FILTERS, sort: 'fact' }, NOW))).toEqual([
      'lead_time',
      'pre_build_weeks',
      'ships_to',
    ])
  })
})

describe('memory chunks', () => {
  it('become rows linked both ways to what was extracted from them', () => {
    const chunk = WITH_CHUNKS.find((r) => r.id === 'chunk:t1')
    expect(chunk).toMatchObject({
      kind: 'chunk',
      role: 'user',
      // An id memory no longer lists ("gone") is left out.
      derived: ['fact:f3', 'relation:r1'],
      entity_types: ['organisation'],
      categories: ['context', 'knowledge'],
    })
    const lead = records(WITH_CHUNKS).find((r) => r.id === 'fact:f3')
    expect(lead?.chunk).toBe('chunk:t1')
    // A fact whose chunk wasn't loaded links nowhere.
    expect(records(WITH_CHUNKS).find((r) => r.id === 'fact:f1')?.chunk).toBeNull()
  })

  it('are searched by their text and filtered by kind', () => {
    expect(keys(applyFilters(WITH_CHUNKS, { ...NO_FILTERS, query: 'six' }, NOW))).toEqual(
      [],
    )
    expect(
      keys(applyFilters(WITH_CHUNKS, { ...NO_FILTERS, query: '6 days' }, NOW)),
    ).toEqual(['Acme ships to Reno; lead time is 6 days.'])
    expect(
      keys(applyFilters(WITH_CHUNKS, { ...NO_FILTERS, kind: 'chunk' }, NOW)),
    ).toEqual(['Noted.', 'Acme ships to Reno; lead time is 6 days.'])
  })

  it('match a type or category through what was taken from them', () => {
    const filters = { ...NO_FILTERS, kind: 'chunk' as const, type: 'organisation' }
    expect(keys(applyFilters(WITH_CHUNKS, filters, NOW))).toEqual([
      'Acme ships to Reno; lead time is 6 days.',
    ])
    expect(facets(WITH_CHUNKS)).toEqual({
      types: ['concept', 'organisation'],
      categories: ['context', 'knowledge'],
    })
  })

  it('counts each kind under every other filter', () => {
    expect(countKinds(WITH_CHUNKS, NO_FILTERS, NOW)).toEqual({
      all: 5,
      fact: 2,
      relation: 1,
      chunk: 2,
      action: 0,
      unknown: 0,
      instruction: 0,
      document: 0,
    })
    // The kind itself never narrows the counts.
    expect(
      countKinds(WITH_CHUNKS, { ...NO_FILTERS, kind: 'fact', query: 'acme' }, NOW),
    ).toEqual({
      all: 3,
      fact: 1,
      relation: 1,
      chunk: 1,
      action: 0,
      unknown: 0,
      instruction: 0,
      document: 0,
    })
  })
})

describe('actions, unknowns and sources', () => {
  const ROWS_ALL = toRows(
    ENTITIES.map((entity) => ({
      ...entity,
      facts: entity.facts.map((f) =>
        f.id === 'f3' ? { ...f, source: { ...SOURCE, kind: 'upsert' } } : f,
      ),
      relations: entity.relations.map((r) => ({
        ...r,
        source: { ...SOURCE, kind: 'elaboration' },
      })),
    })),
    [],
    [
      {
        id: 'a1',
        actor_ref: 'organisation/acme',
        actor_name: 'Acme Logistics',
        verb: 'delayed',
        object_ref: null,
        object_name: 'Reno shipment',
        summary: 'Acme delayed the Reno shipment',
        category: 'context',
        created_at: '2026-11-03T11:00:00+00:00',
        occurred_at: null,
        confidence: 1,
        scopes: ['org/spreetail'],
        source: { ...SOURCE, kind: 'turn' },
      },
    ],
    [
      {
        id: 'u1',
        about: 'It is late again.',
        reason: "'It' is ambiguous",
        resolved: false,
        resolvable: false,
        entity_ref: 'organisation/acme',
        entity_name: 'Acme Logistics',
        key: null,
        scopes: ['org/spreetail'],
        labels: [],
        created_at: '2026-11-03T11:30:00+00:00',
      },
    ],
  )

  it('become rows of their own kinds, searched by what they say', () => {
    expect(keys(applyFilters(ROWS_ALL, { ...NO_FILTERS, kind: 'action' }, NOW))).toEqual([
      'action:a1',
    ])
    expect(
      keys(applyFilters(ROWS_ALL, { ...NO_FILTERS, query: 'ambiguous' }, NOW)),
    ).toEqual(['unknown:u1'])
    // The type filter reaches an action by its actor, an unknown by its entity.
    expect(
      keys(
        applyFilters(
          ROWS_ALL,
          { ...NO_FILTERS, type: 'organisation', kind: 'action' },
          NOW,
        ),
      ),
    ).toEqual(['action:a1'])
    expect(countKinds(ROWS_ALL, NO_FILTERS, NOW)).toMatchObject({ action: 1, unknown: 1 })
  })

  it('filter by where they came from', () => {
    const from = (origin: Origin) =>
      keys(applyFilters(ROWS_ALL, { ...NO_FILTERS, origin }, NOW))
    expect(from('inferred')).toEqual(['ships_to'])
    expect(from('stored')).toEqual(['lead_time'])
    // f1 has no source, so no origin; the action was captured; unknowns have none.
    expect(from('captured')).toEqual(['action:a1'])
  })
})

describe('instructions and documents', () => {
  const rows = toRows(
    [],
    [],
    [],
    [],
    [{ id: 'i1', label: 'methodology_format', description: 'Keep methodology short.' }],
    [
      {
        id: 'd1',
        title: 'Pricing notes',
        file_name: 'pricing%20doc.md',
        mime_type: 'text/markdown',
        size_bytes: 6772,
        status: 'queued',
        error: null,
        created_at: '2026-11-02T12:35:44Z',
        updated_at: '2026-11-02T12:35:44Z',
        processed_at: null,
      },
    ],
  )

  it('belong to no space, so "All" leaves them out and their own kind lists them', () => {
    expect(applyFilters(rows, NO_FILTERS, NOW)).toEqual([])
    expect(countKinds(rows, NO_FILTERS, NOW)).toMatchObject({
      all: 0,
      instruction: 1,
      document: 1,
    })
    expect(
      applyFilters(rows, { ...NO_FILTERS, kind: 'instruction' }, NOW).map((r) => r.id),
    ).toEqual(['instruction:i1'])
    expect(
      applyFilters(rows, { ...NO_FILTERS, kind: 'document' }, NOW).map((r) => r.id),
    ).toEqual(['document:d1'])
  })

  it('search their text; an instruction has no date, so a date window hides it', () => {
    const pick = (kind: 'instruction' | 'document', extra = {}) =>
      applyFilters(rows, { ...NO_FILTERS, kind, ...extra }, NOW).length
    expect(pick('instruction', { query: 'methodology' })).toBe(1)
    // The upload name arrives URL-encoded; it is searched and shown decoded.
    expect(pick('document', { query: 'pricing doc.md' })).toBe(1)
    expect(pick('document', { query: 'queued' })).toBe(1)
    expect(pick('instruction', { since: '7d' })).toBe(0)
    expect(pick('document', { since: '7d' })).toBe(1)
  })
})
