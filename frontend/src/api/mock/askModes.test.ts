import type { AskLayer, LayerName } from '@/api/ask'
import { mockAskApi } from '@/api/mock/ask'
import { applyMode, keyTokens, parseFact } from '@/api/mock/askModes'
import { mockSession, setMockLatencyScale } from '@/api/mock/backend'

beforeAll(() => setMockLatencyScale(0))
afterAll(() => setMockLatencyScale(1))
beforeEach(() => mockSession.set('priya@example.com'))

let id = 0
function layer(name: LayerName, area: string, facts: [string, number][]): AskLayer {
  return {
    layer: name,
    area,
    owner: null,
    error: null,
    facts: facts.map(([text, score]) => ({
      fact: text,
      source: {
        kind: 'memory',
        hit_kind: 'attribute',
        hit_id: `attribute:${++id}`,
        title: null,
        date: null,
        text,
        score,
      },
    })),
  }
}

describe('parseFact', () => {
  it('reads the live Agent Memory shape and the mock shape', () => {
    expect(
      parseFact(
        'attribute',
        "Cobalt Ridge's returns window is within 60 days of delivery",
      ),
    ).toEqual({
      entity: 'Cobalt Ridge',
      key: 'returns window',
      value: 'within 60 days of delivery',
    })
    expect(parseFact('attribute', 'returns policy · window_days = 30')).toEqual({
      entity: 'returns policy',
      key: 'window_days',
      value: '30',
    })
    expect(parseFact('entity', 'Cobalt Ridge')).toBeNull()
    expect(
      parseFact('memory_chunk', "Ops note: Cobalt Ridge's window is 45 days"),
    ).toBeNull()
  })

  it('normalizes keys by plural and synonym, but not across different words', () => {
    expect(keyTokens('max promotional discount')).toEqual(
      keyTokens('maximum promotional discount'),
    )
    expect(keyTokens('warranty_periods')).toEqual(keyTokens('warranty period'))
    expect(keyTokens('return policy')).not.toEqual(keyTokens('returns window'))
  })
})

describe('applyMode', () => {
  const returns = () => [
    layer('org', 'org', [["Lumen Desk Lamp's return window is 30 days", 0.7]]),
    layer('team', 'org/team/ops', [["Lumen Desk Lamp's return window is 45 days", 0.66]]),
    layer('personal', 'org/user/u-0001', [
      ["Lumen Desk Lamp's returns window is 60 days", 0.75],
    ]),
  ]

  it('Default finds nothing; By layer flags but decides nothing', () => {
    expect(applyMode('default', returns(), 0.1).conflicts).toEqual([])
    const view = applyMode('by_layer', returns(), 0.1)
    expect(view.conflicts).toHaveLength(1)
    expect(view.conflicts[0]?.values.map((v) => v.value)).toEqual([
      '60 days',
      '30 days',
      '45 days',
    ])
    expect(view.conflicts[0]?.winner_hit_id).toBeNull()
    expect(view.verdicts.size).toBe(0)
  })

  it('Best match gives a near-tie to the broader layer', () => {
    const view = applyMode('best_match', returns(), 0.1)
    const conflict = view.conflicts[0]!
    expect(conflict.reason).toBe('Scores within 0.10, so the broader Org layer wins')
    const statuses = [...view.verdicts.values()].map((v) => v.status)
    expect(statuses.filter((s) => s === 'used')).toHaveLength(1)
    expect(statuses.filter((s) => s === 'set_aside')).toHaveLength(2)
  })

  it('Best match lets a clearly better personal match win', () => {
    const layers = [
      layer('org', 'org', [["Ferro Cast Pan's restocking fee is 10%", 0.5]]),
      layer('personal', 'org/user/u-0001', [
        ["Ferro Cast Pan's restocking fee is 15%", 0.82],
      ]),
    ]
    const view = applyMode('best_match', layers, 0.1)
    expect(view.conflicts[0]?.reason).toBe('Closest match to the question (0.82 vs 0.50)')
    expect(view.verdicts.get(layers[1]!.facts[0]!.source.hit_id)?.status).toBe('used')
  })

  it('two values inside one scope are not a conflict', () => {
    const layers = [
      layer('team', 'org/team/ops', [
        ["Sable Kettle's safety stock is 200 units", 0.6],
        ["Sable Kettle line's safety stock is 250 units", 0.58],
      ]),
    ]
    expect(applyMode('by_layer', layers, 0.1).conflicts).toEqual([])
  })
})

describe('mock ask modes', () => {
  it('echoes the mode, falls back to default, and marks facts in a conflict', async () => {
    const plain = await mockAskApi.ask({ q: 'What is the returns window?' })
    expect(plain).toMatchObject({ mode: 'default', mode_source: 'config', conflicts: [] })

    const best = await mockAskApi.ask({
      q: 'What is the returns window?',
      mode: 'best_match',
    })
    expect(best).toMatchObject({ mode: 'best_match', mode_source: 'request' })
    expect(best.metadata.tie_margin).toBe(0.1)
    expect(best.conflicts).toHaveLength(1)
    const facts = best.layers.flatMap((l) => l.facts).filter((f) => f.conflict_id)
    expect(facts.map((f) => f.status).sort()).toEqual(['set_aside', 'used'])
  })
})
