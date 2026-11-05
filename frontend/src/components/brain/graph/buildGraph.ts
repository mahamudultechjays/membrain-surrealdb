import {
  isRecord,
  type BrainRow,
  type ChunkRow,
  type RecordRow,
} from '@/components/brain/filter'
import { CHUNK_COLOR, colorFor } from '@/components/brain/graph/canvasTheme'
import { CHUNK_EDGE_LABEL } from '@/components/brain/graph/forces'

/*
 * The graph Brain draws, built from the rows its filters already produced, so
 * every filter (and the spaces the backend allowed) applies to it too:
 *
 * - each entity with a fact or relation in view is a node;
 * - each relation is an edge, subject -> object. An object entity with
 *   nothing of its own in view is still drawn, as a "ghost", so no edge
 *   points at nothing;
 * - each memory chunk in view is a small node, linked to the entities whose
 *   facts were extracted from it.
 */

export type NodeKind = 'entity' | 'ghost' | 'chunk'

export interface GraphNodeData {
  kind: NodeKind
  /** Entity name, or the start of a chunk's text. */
  name: string
  /** Entity type; "chunk" for chunks. */
  type: string
  /** Facts and relations of this entity in view (empty for ghosts and chunks). */
  records: RecordRow[]
  chunk: ChunkRow | null
  degree: number
  /** The entity's "type/key" ref; null for chunks. */
  ref: string | null
  /** Every space its facts, relations or text were saved in. */
  scopes: string[]
  /** When memory last learned something about it. */
  updated: string
}

export interface GraphNode {
  id: string
  label: string
  fill: string
  size: number
  data: GraphNodeData
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  /** The relation's name; blank to leave the line uncaptioned. */
  label: string
  data: GraphEdgeData
}

export interface GraphEdgeData {
  /** The relation this edge draws; null for a chunk's link to an entity. */
  relation: RecordRow | null
  /** Display names of the two ends, for the hover card. */
  from: string
  to: string
}

export interface BrainGraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

const entityId = (ref: string) => `e:${ref}`
/** Labels run to 42 characters, as in membrain: longer ones overprint each other. */
const caption = (text: string) => {
  const flat = text.replace(/\s+/g, ' ').trim()
  return flat.length > 42 ? `${flat.slice(0, 40)}…` : flat
}

export function buildGraph(rows: readonly BrainRow[]): BrainGraphData {
  const nodes = new Map<string, GraphNodeData>()
  const edges = new Map<string, GraphEdge>()

  const entity = (ref: string, name: string, type: string, kind: NodeKind) => {
    const id = entityId(ref)
    const found = nodes.get(id)
    if (found) {
      // Seen first as a relation's target: it has rows of its own after all.
      if (kind === 'entity' && found.kind === 'ghost')
        Object.assign(found, { kind, name, type })
      return found
    }
    const made: GraphNodeData = {
      kind,
      name,
      type,
      records: [],
      chunk: null,
      degree: 0,
      ref,
      scopes: [],
      updated: '',
    }
    nodes.set(id, made)
    return made
  }

  const records = rows.filter(isRecord)
  for (const row of records) {
    if (!row.entity_ref) continue
    entity(row.entity_ref, row.entity, row.entity_type, 'entity').records.push(row)
  }
  for (const row of records) {
    if (row.kind !== 'relation' || !row.entity_ref || !row.value_ref) continue
    const [type = ''] = row.value_ref.split('/')
    entity(row.value_ref, row.value, type, 'ghost')
    edges.set(row.id, {
      id: row.id,
      source: entityId(row.entity_ref),
      target: entityId(row.value_ref),
      label: row.key,
      data: { relation: row, from: row.entity, to: row.value },
    })
  }

  const byId = new Map(records.map((r) => [r.id, r]))
  for (const chunk of rows.filter((r): r is ChunkRow => r.kind === 'chunk')) {
    const id = `c:${chunk.record_id}`
    nodes.set(id, {
      kind: 'chunk',
      name: chunk.text,
      type: 'chunk',
      records: [],
      chunk,
      degree: 0,
      ref: null,
      scopes: chunk.scopes,
      updated: chunk.created_at,
    })
    for (const rowId of chunk.derived) {
      const row = byId.get(rowId)
      const ref = row?.entity_ref
      if (!row || !ref || !nodes.has(entityId(ref))) continue
      // Prefixed like the chunk's own id, which is how forces tell these apart.
      const edgeId = `${id}->${ref}`
      edges.set(edgeId, {
        id: edgeId,
        source: id,
        target: entityId(ref),
        label: CHUNK_EDGE_LABEL,
        data: { relation: null, from: 'Memory chunk', to: row.entity },
      })
    }
  }

  for (const edge of edges.values()) {
    for (const end of [edge.source, edge.target]) {
      const node = nodes.get(end)
      if (node) node.degree += 1
    }
  }

  for (const data of nodes.values()) {
    if (data.kind === 'chunk') continue
    data.scopes = [...new Set(data.records.flatMap((r) => r.scopes))].sort()
    data.updated = data.records.reduce(
      (max, r) => (r.created_at > max ? r.created_at : max),
      '',
    )
  }

  return {
    nodes: [...nodes].map(([id, data]) => ({
      id,
      label: caption(data.name),
      fill: data.kind === 'chunk' ? CHUNK_COLOR : colorFor(data.type),
      size: sizeOf(data),
      data,
    })),
    edges: [...edges.values()],
  }
}

/** Bigger the more memory holds about it; chunks and ghosts stay small. */
function sizeOf(data: GraphNodeData): number {
  if (data.kind === 'chunk') return 3
  if (data.kind === 'ghost') return 4
  return 5 + Math.min(data.records.length + data.degree, 26) / 2
}

/** How much a node matters when the canvas can't draw everything. */
const weight = (node: GraphNode) => node.data.degree * 2 + node.data.records.length

/**
 * At most `limit` nodes: the best-connected first, with the edges between the
 * ones kept. A thousand-relation brain drawn whole is a hairball; this is the
 * overview, and focusing a node shows its neighbourhood in full.
 */
export function limitGraph(graph: BrainGraphData, limit: number): BrainGraphData {
  if (graph.nodes.length <= limit) return graph
  const kept = new Set(
    [...graph.nodes]
      .sort((a, b) => weight(b) - weight(a) || a.label.localeCompare(b.label))
      .slice(0, limit)
      .map((n) => n.id),
  )
  return induced(graph, kept)
}

/** The node, everything within `depth` hops of it (either direction), and the edges among them. */
export function egoGraph(
  graph: BrainGraphData,
  center: string,
  depth: number,
): BrainGraphData {
  const around = new Map<string, string[]>()
  for (const e of graph.edges) {
    around.set(e.source, [...(around.get(e.source) ?? []), e.target])
    around.set(e.target, [...(around.get(e.target) ?? []), e.source])
  }
  const kept = new Set([center])
  let frontier = [center]
  for (let hop = 0; hop < depth; hop++) {
    frontier = frontier
      .flatMap((id) => around.get(id) ?? [])
      .filter((id) => !kept.has(id))
    for (const id of frontier) kept.add(id)
  }
  return induced(graph, kept)
}

function induced(graph: BrainGraphData, kept: ReadonlySet<string>): BrainGraphData {
  return {
    nodes: graph.nodes.filter((n) => kept.has(n.id)),
    edges: graph.edges.filter((e) => kept.has(e.source) && kept.has(e.target)),
  }
}

/**
 * The edges with names left only on those touching `center`: a focused node's
 * own relations read as spokes, and the web between its neighbours stays quiet
 * (hover a line for its name).
 */
export function captionSpokes(edges: readonly GraphEdge[], center: string): GraphEdge[] {
  return edges.map((e) =>
    e.source === center || e.target === center || !e.label ? e : { ...e, label: '' },
  )
}

export interface Connection {
  edge: GraphEdge
  /** True when the node is the edge's subject. */
  outgoing: boolean
  /** The name at the other end. */
  other: string
}

/** A node's connections, outgoing first, each with the name at its far end. */
export function connectionsOf(edges: readonly GraphEdge[], id: string): Connection[] {
  const out: Connection[] = []
  const into: Connection[] = []
  for (const edge of edges) {
    if (edge.source === id) out.push({ edge, outgoing: true, other: edge.data.to })
    else if (edge.target === id)
      into.push({ edge, outgoing: false, other: edge.data.from })
  }
  return [...out, ...into]
}

/** The drawn size range, so reagraph keeps sizes as given rather than rescaling them. */
export function sizeBounds(nodes: readonly GraphNode[]): { min: number; max: number } {
  const sizes = nodes.map((n) => n.size)
  return sizes.length
    ? { min: Math.min(...sizes), max: Math.max(...sizes) }
    : { min: 5, max: 5 }
}

/** The entity types drawn, most common first, for the legend. */
export function typesShown(
  nodes: readonly GraphNode[],
): { type: string; fill: string; count: number }[] {
  const counts = new Map<string, { fill: string; count: number }>()
  for (const n of nodes) {
    const found = counts.get(n.data.type) ?? { fill: n.fill, count: 0 }
    found.count += 1
    counts.set(n.data.type, found)
  }
  return [...counts]
    .map(([type, v]) => ({ type, ...v }))
    .sort((a, b) => b.count - a.count || a.type.localeCompare(b.type))
}
