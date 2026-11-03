import type { AskLayer } from '@/api/ask'
import { findConflicts } from '@/components/ask/conflicts'

function layer(
  name: AskLayer['layer'],
  area: string,
  owner: string | null,
  facts: string[],
) {
  return {
    layer: name,
    area,
    owner,
    error: null,
    facts: facts.map((fact, i) => ({
      fact,
      source: {
        kind: 'memory' as const,
        hit_kind: 'attribute',
        hit_id: `${area}-${i}`,
        title: null,
        date: null,
        text: fact,
        score: 0.5,
      },
    })),
  }
}

describe('findConflicts', () => {
  it('flags the same entity with different values across layers', () => {
    const conflicts = findConflicts([
      layer('org', 'org', null, ['returns policy · window_days = 30', 'free text fact']),
      layer('personal', 'org/user/u-0001', 'Priya', [
        'Returns policy · window_days = 60',
      ]),
    ])

    expect(conflicts).toEqual([
      {
        entity: 'returns policy · window_days',
        values: [
          { value: '30', layers: ['Org'] },
          { value: '60', layers: ["Priya's personal"] },
        ],
      },
    ])
  })

  it('ignores agreement across layers and disagreement within one layer', () => {
    expect(
      findConflicts([
        layer('org', 'org', null, ['a · b = 1', 'c · d = 1', 'c · d = 2']),
        layer('team', 'org/team/ops', null, ['a · b = 1']),
      ]),
    ).toEqual([])
  })
})
