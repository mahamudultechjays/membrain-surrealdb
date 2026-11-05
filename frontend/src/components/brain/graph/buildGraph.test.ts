import type { BrainChunk, BrainEntity } from '@/api/brain'
import { toRows } from '@/components/brain/filter'
import {
  buildGraph,
  captionSpokes,
  connectionsOf,
  egoGraph,
  limitGraph,
  sizeBounds,
  typesShown,
} from '@/components/brain/graph/buildGraph'

const AT = '2026-11-03T10:00:00+00:00'
const SCOPES = ['org/spreetail']

const fact = (id: string, key: string, turn?: string) => ({
  id,
  key,
  value: `${key} value`,
  category: 'context',
  scopes: SCOPES,
  created_at: AT,
  replaced: false,
  summary: null,
  labels: [],
  source: turn
    ? { kind: 'turn', ref: `turn:${turn}`, session_id: 's', trust: 0.5 }
    : undefined,
})

const relation = (
  id: string,
  label: string,
  object_ref: string,
  object_name: string,
) => ({
  id,
  label,
  object_ref,
  object_name,
  category: 'context',
  scopes: SCOPES,
  created_at: AT,
  summary: null,
  labels: [],
})

const entity = (
  ref: string,
  name: string,
  facts: ReturnType<typeof fact>[],
  relations: ReturnType<typeof relation>[] = [],
): BrainEntity => ({
  ref,
  name,
  entity_type: ref.split('/')[0]!,
  category: 'knowledge',
  scopes: SCOPES,
  updated_at: AT,
  facts,
  relations,
})

const ENTITIES = [
  entity(
    'organisation/acme',
    'Acme Logistics',
    [fact('f1', 'lead_time', 't1')],
    [
      relation('r1', 'ships_to', 'location/reno', 'Reno warehouse'),
      relation('r2', 'owned_by', 'organisation/holdco', 'HoldCo'),
    ],
  ),
  entity(
    'location/reno',
    'Reno warehouse',
    [fact('f2', 'dock_count')],
    [relation('r3', 'near', 'location/sparks', 'Sparks')],
  ),
]

const CHUNKS: BrainChunk[] = [
  {
    id: 't1',
    session_id: 's',
    role: 'user',
    text: 'Acme ships to Reno in 6 days.',
    created_at: AT,
    scopes: SCOPES,
    derived: ['f1'],
  },
]

const GRAPH = buildGraph(toRows(ENTITIES, CHUNKS))
const ids = (g: { nodes: { id: string }[] }) => g.nodes.map((n) => n.id).sort()

describe('buildGraph', () => {
  it('draws entities as nodes and relations as edges, with ghosts for bare targets', () => {
    expect(ids(GRAPH)).toEqual([
      'c:t1',
      'e:location/reno',
      'e:location/sparks',
      'e:organisation/acme',
      'e:organisation/holdco',
    ])
    const byId = new Map(GRAPH.nodes.map((n) => [n.id, n]))
    // Reno has rows of its own, so it is an entity even though r1 named it first.
    expect(byId.get('e:location/reno')?.data.kind).toBe('entity')
    expect(byId.get('e:organisation/holdco')?.data).toMatchObject({
      kind: 'ghost',
      name: 'HoldCo',
      type: 'organisation',
    })
    expect(byId.get('e:organisation/acme')?.data.records.map((r) => r.id)).toEqual([
      'fact:f1',
      'relation:r1',
      'relation:r2',
    ])
    const r1 = GRAPH.edges.find((e) => e.id === 'relation:r1')
    expect(r1).toMatchObject({
      source: 'e:organisation/acme',
      target: 'e:location/reno',
      label: 'ships_to',
      data: { from: 'Acme Logistics', to: 'Reno warehouse' },
    })
    expect(r1?.data.relation?.id).toBe('relation:r1')
  })

  it('hangs each chunk off the entities extracted from it', () => {
    expect(GRAPH.edges).toContainEqual({
      id: 'c:t1->organisation/acme',
      source: 'c:t1',
      target: 'e:organisation/acme',
      label: 'about',
      data: { relation: null, from: 'Memory chunk', to: 'Acme Logistics' },
    })
    const acme = GRAPH.nodes.find((n) => n.id === 'e:organisation/acme')
    // Two relations out, one chunk in.
    expect(acme?.data.degree).toBe(3)
    // The busiest entity draws biggest; chunks and ghosts stay small.
    expect(sizeBounds(GRAPH.nodes)).toEqual({ min: 3, max: acme?.size })
  })

  it('keeps the best-connected nodes when there are too many to draw', () => {
    const top = limitGraph(GRAPH, 2)
    expect(ids(top)).toEqual(['e:location/reno', 'e:organisation/acme'])
    expect(top.edges.map((e) => e.id)).toEqual(['relation:r1'])
    expect(limitGraph(GRAPH, 50)).toBe(GRAPH)
  })

  it('cuts out a neighbourhood one or two hops deep, either direction', () => {
    expect(ids(egoGraph(GRAPH, 'e:location/sparks', 1))).toEqual([
      'e:location/reno',
      'e:location/sparks',
    ])
    expect(ids(egoGraph(GRAPH, 'e:location/sparks', 2))).toEqual([
      'e:location/reno',
      'e:location/sparks',
      'e:organisation/acme',
    ])
  })

  it('names only the focused node’s own edges, and lists its connections both ways', () => {
    const reno = 'e:location/reno'
    const named = captionSpokes(GRAPH.edges, reno)
    const label = (id: string) => named.find((e) => e.id === id)?.label
    expect(label('relation:r1')).toBe('ships_to') // Acme -> Reno
    expect(label('relation:r3')).toBe('near') // Reno -> Sparks
    expect(label('relation:r2')).toBe('') // Acme -> HoldCo: not Reno's
    // The originals are left alone.
    expect(GRAPH.edges.find((e) => e.id === 'relation:r2')?.label).toBe('owned_by')

    expect(
      connectionsOf(GRAPH.edges, reno).map((c) => [c.edge.label, c.outgoing, c.other]),
    ).toEqual([
      ['near', true, 'Sparks'],
      ['ships_to', false, 'Acme Logistics'],
    ])
  })

  it('lists the types drawn, most common first', () => {
    expect(typesShown(GRAPH.nodes).map((t) => [t.type, t.count])).toEqual([
      ['location', 2],
      ['organisation', 2],
      ['chunk', 1],
    ])
  })
})
