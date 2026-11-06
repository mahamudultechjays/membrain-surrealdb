import type {
  BrainAction,
  BrainChunk,
  BrainDocument,
  BrainEntity,
  BrainInstruction,
  BrainSource,
  BrainUnknown,
} from '@/api/brain'
import type { FactTags } from '@/api/vct'

export type Since = 'any' | '1d' | '7d' | '30d'
export type SortBy = 'latest' | 'oldest' | 'entity' | 'fact'
export type Kind =
  | 'all'
  | 'fact'
  | 'relation'
  | 'chunk'
  | 'action'
  | 'unknown'
  | 'instruction'
  | 'document'

/**
 * Kinds Agent Memory keeps with no scope: they belong to no space, so "All"
 * (what is in the spaces picked) leaves them out; picking the kind lists them.
 */
export const UNSCOPED_KINDS: ReadonlySet<Kind> = new Set(['instruction', 'document'])

/**
 * How a record came to be in memory, from its source kind: captured from what
 * someone wrote, inferred by Agent Memory (its elaborate job), merged by its
 * consolidate job, or stored as given (an upsert of reviewed facts).
 */
export type Origin = 'captured' | 'inferred' | 'consolidated' | 'stored'

export const ORIGINS: readonly { value: Origin; label: string }[] = [
  { value: 'captured', label: 'Captured' },
  { value: 'inferred', label: 'Inferred' },
  { value: 'consolidated', label: 'Consolidated' },
  { value: 'stored', label: 'Stored directly' },
]

const ORIGIN_OF: Record<string, Origin> = {
  turn: 'captured',
  elaboration: 'inferred',
  reflection: 'inferred',
  consolidation: 'consolidated',
  upsert: 'stored',
}

/** A source's origin; null when Agent Memory doesn't say or uses a kind not known here. */
export const originOf = (source: BrainSource | null | undefined): Origin | null =>
  (source?.kind && ORIGIN_OF[source.kind]) || null

interface RowBase {
  /** Unique across every kind: "fact:…", "relation:…", "chunk:…", "action:…", "unknown:…". */
  id: string
  scopes: string[]
  created_at: string
  /** Where the row came from; null for unknowns, which no capture produced. */
  origin: Origin | null
}

/** One fact or relation, as a row of its own. */
export interface RecordRow extends RowBase {
  kind: 'fact' | 'relation'
  entity: string
  entity_type: string
  /** A fact's key, or a relation's label. */
  key: string
  /** A fact's value, or the related entity's name. */
  value: string
  category: string
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
  /** The row id of the memory chunk this was extracted from, when it is loaded. */
  chunk: string | null
  /** A fact's active VCT node and goal; never set on relations. */
  vct?: FactTags | null
  /** False until the VCT tagger has handled the fact. */
  vct_tagged?: boolean
}

/** A memory chunk: the text of one captured turn. */
export interface ChunkRow extends RowBase {
  kind: 'chunk'
  text: string
  role: string
  session_id: string
  /** The turn's id. */
  record_id: string
  /** Row ids of the facts and relations extracted from this text. */
  derived: string[]
  /** The entity types and categories of those, so the same filters apply. */
  entity_types: string[]
  categories: string[]
}

/** A dated event memory recorded: actor → verb → object. */
export interface ActionRow extends RowBase {
  kind: 'action'
  actor: string
  /** The actor entity's type, so the type filter applies. */
  actor_type: string
  verb: string
  /** The object entity's name, or the action's free-text object. */
  object: string | null
  summary: string | null
  category: string
  occurred_at: string | null
  confidence: number | null
  source: BrainSource | null
  record_id: string
  /** The row id of the memory chunk it was taken from, when that is loaded. */
  chunk: string | null
}

/** Something memory could not settle: an unclear reference, or a contradiction. */
export interface UnknownRow extends RowBase {
  kind: 'unknown'
  about: string
  reason: string
  resolved: boolean
  resolvable: boolean
  /** The entity it concerns, when it concerns one. */
  entity: string | null
  entity_type: string | null
  key: string | null
  labels: string[]
  record_id: string
}

/** A standing rule memory follows. No scope and no date: it applies everywhere. */
export interface InstructionRow extends RowBase {
  kind: 'instruction'
  label: string
  description: string
  record_id: string
}

/** A file uploaded to memory, with how far Agent Memory has got reading it. */
export interface DocumentRow extends RowBase {
  kind: 'document'
  title: string
  file_name: string
  mime_type: string
  size_bytes: number | null
  /** queued, processing, done or failed. */
  status: string
  error: string | null
  updated_at: string
  processed_at: string | null
  record_id: string
}

export type BrainRow =
  RecordRow | ChunkRow | ActionRow | UnknownRow | InstructionRow | DocumentRow

/** Facts and relations: the rows that belong to an entity. */
export const isRecord = (row: BrainRow): row is RecordRow =>
  row.kind === 'fact' || row.kind === 'relation'

export interface BrainFilters {
  /** Matches the entity, the key or label, the value, the summary and chunk text. */
  query: string
  kind: Kind
  /** An entity type, or '' for all. A chunk matches through what was taken from it. */
  type: string
  /** A memory category, or '' for all. */
  category: string
  since: Since
  sort: SortBy
  /** Show facts a newer value has replaced. */
  showReplaced: boolean
  /** Where rows came from, or '' for anywhere. */
  origin: Origin | ''
}

export const NO_FILTERS: BrainFilters = {
  query: '',
  kind: 'all',
  type: '',
  category: '',
  since: 'any',
  sort: 'latest',
  showReplaced: false,
  origin: '',
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

/** Upload names can arrive URL-encoded ("Membrain%20-%20WS.txt"); show them plainly. */
function decodeName(name: string): string {
  try {
    return decodeURIComponent(name)
  } catch {
    return name
  }
}

/** Every record memory holds, of every kind, as one flat list. */
export function toRows(
  entities: readonly BrainEntity[],
  chunks: readonly BrainChunk[] = [],
  actions: readonly BrainAction[] = [],
  unknowns: readonly BrainUnknown[] = [],
  instructions: readonly BrainInstruction[] = [],
  documents: readonly BrainDocument[] = [],
): BrainRow[] {
  const turnIds = new Set(chunks.map((c) => c.id))
  const chunkOf = (source: BrainSource | undefined) => {
    const turn = source?.ref?.startsWith('turn:') ? source.ref.slice(5) : null
    return turn && turnIds.has(turn) ? `chunk:${turn}` : null
  }

  const records: RecordRow[] = entities.flatMap((entity) => [
    ...entity.facts.map((fact): RecordRow => ({
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
      chunk: chunkOf(fact.source),
      origin: originOf(fact.source),
      vct: fact.vct ?? null,
      vct_tagged: fact.vct_tagged ?? false,
    })),
    ...entity.relations.map((relation): RecordRow => ({
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
      chunk: chunkOf(relation.source),
      origin: originOf(relation.source),
    })),
  ])

  const byRecordId = new Map(records.map((row) => [row.record_id, row]))
  const chunkRows = chunks.map((chunk): ChunkRow => {
    const derived = chunk.derived.flatMap((id) => byRecordId.get(id) ?? [])
    return {
      id: `chunk:${chunk.id}`,
      kind: 'chunk',
      text: chunk.text,
      role: chunk.role,
      session_id: chunk.session_id,
      record_id: chunk.id,
      scopes: chunk.scopes,
      created_at: chunk.created_at,
      derived: derived.map((row) => row.id),
      entity_types: distinct(derived.map((row) => row.entity_type)),
      categories: distinct(derived.map((row) => row.category)),
      origin: 'captured',
    }
  })
  const actionRows = actions.map((action): ActionRow => ({
    id: `action:${action.id}`,
    kind: 'action',
    actor: action.actor_name,
    actor_type: action.actor_ref.split('/')[0] ?? '',
    verb: action.verb,
    object: action.object_name,
    summary: action.summary,
    category: action.category,
    scopes: action.scopes,
    created_at: action.created_at,
    occurred_at: action.occurred_at,
    confidence: action.confidence,
    source: action.source,
    record_id: action.id,
    chunk: chunkOf(action.source),
    origin: originOf(action.source),
  }))
  const unknownRows = unknowns.map((unknown): UnknownRow => ({
    id: `unknown:${unknown.id}`,
    kind: 'unknown',
    about: unknown.about,
    reason: unknown.reason,
    resolved: unknown.resolved,
    resolvable: unknown.resolvable,
    entity: unknown.entity_name,
    entity_type: unknown.entity_ref?.split('/')[0] ?? null,
    key: unknown.key,
    labels: unknown.labels,
    scopes: unknown.scopes,
    created_at: unknown.created_at,
    record_id: unknown.id,
    origin: null,
  }))
  const instructionRows = instructions.map((instruction): InstructionRow => ({
    id: `instruction:${instruction.id}`,
    kind: 'instruction',
    label: instruction.label,
    description: instruction.description,
    record_id: instruction.id,
    scopes: [],
    created_at: '',
    origin: null,
  }))
  const documentRows = documents.map((doc): DocumentRow => ({
    id: `document:${doc.id}`,
    kind: 'document',
    title: doc.title,
    file_name: decodeName(doc.file_name),
    mime_type: doc.mime_type,
    size_bytes: doc.size_bytes,
    status: doc.status,
    error: doc.error,
    updated_at: doc.updated_at,
    processed_at: doc.processed_at,
    record_id: doc.id,
    scopes: [],
    created_at: doc.created_at,
    origin: null,
  }))
  return [
    ...records,
    ...chunkRows,
    ...actionRows,
    ...unknownRows,
    ...instructionRows,
    ...documentRows,
  ]
}

function searchable(row: BrainRow): string[] {
  switch (row.kind) {
    case 'chunk':
      return [row.text]
    case 'action':
      return [row.actor, row.verb, row.object ?? '', row.summary ?? '']
    case 'unknown':
      return [row.about, row.reason, row.entity ?? '', row.key ?? '']
    case 'instruction':
      return [row.label, row.description]
    case 'document':
      return [row.title, row.file_name, row.status]
    default:
      return [row.entity, row.key, row.value, row.summary ?? '']
  }
}
function typesOf(row: BrainRow): string[] {
  switch (row.kind) {
    case 'chunk':
      return row.entity_types
    case 'action':
      return [row.actor_type]
    case 'unknown':
      return row.entity_type ? [row.entity_type] : []
    case 'instruction':
    case 'document':
      return []
    default:
      return [row.entity_type]
  }
}
function categoriesOf(row: BrainRow): string[] {
  switch (row.kind) {
    case 'chunk':
      return row.categories
    case 'unknown':
    case 'instruction':
    case 'document':
      return []
    default:
      return [row.category]
  }
}
/** What "Entity A–Z" sorts a row by; a chunk by its text, an action by its actor. */
function entityOf(row: BrainRow): string {
  switch (row.kind) {
    case 'chunk':
      return row.text
    case 'action':
      return row.actor
    case 'unknown':
      return row.entity ?? row.about
    case 'instruction':
      return row.label
    case 'document':
      return row.title
    default:
      return row.entity
  }
}
/** What "Fact A–Z" sorts a row by. */
function keyOf(row: BrainRow): string {
  switch (row.kind) {
    case 'chunk':
      return row.text
    case 'action':
      return row.verb
    case 'unknown':
      return row.key ?? row.about
    case 'instruction':
      return row.label
    case 'document':
      return row.title
    default:
      return row.key
  }
}

/** True when the row passes every filter but the kind. */
function passes(row: BrainRow, filters: BrainFilters, query: string, cutoff: number) {
  return (
    (filters.showReplaced || !isRecord(row) || !row.replaced) &&
    (!filters.origin || row.origin === filters.origin) &&
    (!filters.type || typesOf(row).includes(filters.type)) &&
    (!filters.category || categoriesOf(row).includes(filters.category)) &&
    (filters.since === 'any' || parseDate(row.created_at) >= cutoff) &&
    (!query || searchable(row).some((text) => text.toLowerCase().includes(query)))
  )
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
      (filters.kind === 'all'
        ? !UNSCOPED_KINDS.has(row.kind)
        : row.kind === filters.kind) && passes(row, filters, query, cutoff),
  )

  const byDate = (a: BrainRow, b: BrainRow) =>
    parseDate(b.created_at) - parseDate(a.created_at)
  const sorters: Record<SortBy, (a: BrainRow, b: BrainRow) => number> = {
    latest: byDate,
    oldest: (a, b) => -byDate(a, b),
    entity: (a, b) => entityOf(a).localeCompare(entityOf(b)) || byDate(a, b),
    fact: (a, b) => keyOf(a).localeCompare(keyOf(b)) || byDate(a, b),
  }
  return shown.sort(sorters[filters.sort])
}

/**
 * How many rows of each kind pass every other filter: the counts on the kind
 * switch, so each says what picking that kind would show.
 */
export function countKinds(
  rows: readonly BrainRow[],
  filters: BrainFilters,
  now: number = Date.now(),
): Record<Kind, number> {
  const query = filters.query.trim().toLowerCase()
  const cutoff = now - WINDOWS[filters.since]
  const counts: Record<Kind, number> = {
    all: 0,
    fact: 0,
    relation: 0,
    chunk: 0,
    action: 0,
    unknown: 0,
    instruction: 0,
    document: 0,
  }
  for (const row of rows) {
    if (!passes(row, filters, query, cutoff)) continue
    if (!UNSCOPED_KINDS.has(row.kind)) counts.all += 1
    counts[row.kind] += 1
  }
  return counts
}

/** The entity types and categories rows carry, for the filter menus. */
export function facets(rows: readonly BrainRow[]): {
  types: string[]
  categories: string[]
} {
  return {
    types: distinct(rows.flatMap(typesOf)),
    categories: distinct(rows.flatMap(categoriesOf)),
  }
}

/** Distinct values for a filter dropdown, alphabetically. */
export function distinct(values: Iterable<string>): string[] {
  return [...new Set([...values].filter(Boolean))].sort((a, b) => a.localeCompare(b))
}
