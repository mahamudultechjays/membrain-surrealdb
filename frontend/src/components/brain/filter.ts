import type { BrainEntity, BrainSource } from '@/api/brain'

export type Since = 'any' | '1d' | '7d' | '30d'
export type SortBy = 'latest' | 'oldest' | 'entity' | 'fact'
export type Kind = 'all' | 'fact' | 'relation'

/** One fact or relation, as a row of its own. */
export interface BrainRow {
  /** Unique across facts and relations. */
  id: string
  kind: 'fact' | 'relation'
  entity: string
  entity_type: string
  /** A fact's key, or a relation's label. */
  key: string
  /** A fact's value, or the related entity's name. */
  value: string
  category: string
  scopes: string[]
  created_at: string
  /** A fact a newer value replaced; never set on relations. */
  replaced: boolean
  /** Agent Memory's one-sentence version; null when it has none. */
  summary: string | null
  labels: string[]
  /** The rest of what Agent Memory keeps; null when it doesn't say. */
  record_id: string
  entity_ref: string | null
  /** A relation's target entity ref. */
  value_ref: string | null
  confidence: number | null
  importance: number | null
  supersedes: string | null
  superseded_by: string | null
  valid_from: string | null
  valid_until: string | null
  source: BrainSource | null
}

export interface BrainFilters {
  /** Matches the entity, the key or label, the value and the summary. */
  query: string
  kind: Kind
  /** An entity type, or '' for all. */
  type: string
  /** A memory category, or '' for all. */
  category: string
  since: Since
  sort: SortBy
  /** Show facts a newer value has replaced. */
  showReplaced: boolean
}

export const NO_FILTERS: BrainFilters = {
  query: '',
  kind: 'all',
  type: '',
  category: '',
  since: 'any',
  sort: 'latest',
  showReplaced: false,
}

const DAY_MS = 24 * 60 * 60 * 1000
const WINDOWS: Record<Since, number> = {
  any: Infinity,
  '1d': DAY_MS,
  '7d': 7 * DAY_MS,
  '30d': 30 * DAY_MS,
}

/**
 * Agent Memory writes nanosecond timestamps ("…:39.443258276+00:00"), which
 * Date can't parse; keep milliseconds.
 */
export function parseDate(value: string): number {
  const time = Date.parse(value.replace(/(\.\d{3})\d+/, '$1'))
  return Number.isNaN(time) ? 0 : time
}

/** Every fact and relation of every entity, as one flat list. */
export function toRows(entities: readonly BrainEntity[]): BrainRow[] {
  return entities.flatMap((entity) => [
    ...entity.facts.map((fact): BrainRow => ({
      id: `fact:${fact.id}`,
      kind: 'fact',
      entity: entity.name,
      entity_type: entity.entity_type,
      key: fact.key,
      value: fact.value,
      category: fact.category,
      scopes: fact.scopes,
      created_at: fact.created_at,
      replaced: fact.replaced,
      summary: fact.summary,
      labels: fact.labels,
      record_id: fact.id,
      entity_ref: fact.entity_ref ?? entity.ref,
      value_ref: null,
      confidence: fact.confidence ?? null,
      importance: fact.importance ?? null,
      supersedes: fact.supersedes ?? null,
      superseded_by: fact.superseded_by ?? null,
      valid_from: fact.valid_from ?? null,
      valid_until: fact.valid_until ?? null,
      source: fact.source ?? null,
    })),
    ...entity.relations.map((relation): BrainRow => ({
      id: `relation:${relation.id}`,
      kind: 'relation',
      entity: entity.name,
      entity_type: entity.entity_type,
      key: relation.label,
      value: relation.object_name,
      category: relation.category,
      scopes: relation.scopes,
      created_at: relation.created_at,
      replaced: false,
      summary: relation.summary,
      labels: relation.labels,
      record_id: relation.id,
      entity_ref: relation.subject_ref ?? entity.ref,
      value_ref: relation.object_ref,
      confidence: relation.confidence ?? null,
      importance: null,
      supersedes: null,
      superseded_by: null,
      valid_from: relation.valid_from ?? null,
      valid_until: relation.valid_until ?? null,
      source: relation.source ?? null,
    })),
  ])
}

/** The rows that pass the filters, in the chosen order. `now` pins the date windows in tests. */
export function applyFilters(
  rows: readonly BrainRow[],
  filters: BrainFilters,
  now: number = Date.now(),
): BrainRow[] {
  const query = filters.query.trim().toLowerCase()
  const cutoff = now - WINDOWS[filters.since]
  const shown = rows.filter(
    (row) =>
      (filters.kind === 'all' || row.kind === filters.kind) &&
      (filters.showReplaced || !row.replaced) &&
      (!filters.type || row.entity_type === filters.type) &&
      (!filters.category || row.category === filters.category) &&
      (filters.since === 'any' || parseDate(row.created_at) >= cutoff) &&
      (!query ||
        [row.entity, row.key, row.value, row.summary ?? ''].some((text) =>
          text.toLowerCase().includes(query),
        )),
  )

  const byDate = (a: BrainRow, b: BrainRow) =>
    parseDate(b.created_at) - parseDate(a.created_at)
  const sorters: Record<SortBy, (a: BrainRow, b: BrainRow) => number> = {
    latest: byDate,
    oldest: (a, b) => -byDate(a, b),
    entity: (a, b) => a.entity.localeCompare(b.entity) || byDate(a, b),
    fact: (a, b) => a.key.localeCompare(b.key) || byDate(a, b),
  }
  return shown.sort(sorters[filters.sort])
}

/** Distinct values for a filter dropdown, alphabetically. */
export function distinct(values: Iterable<string>): string[] {
  return [...new Set([...values].filter(Boolean))].sort((a, b) => a.localeCompare(b))
}
