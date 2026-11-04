import type { LabRun } from '@/api/lab'
import { clearLabResults } from '@/components/admin/labResults'

const RUN: LabRun = {
  action: 'consolidate',
  scope: 'org/spreetail/lab/ske-a',
  before: { entities: 1, attributes: 29, relations: 51, by_source: {} },
  after: { entities: 1, attributes: 29, relations: 51, by_source: {} },
  outcome: { summary: { created: 7 }, items: [], text: null, trace_ids: [] },
  latency_ms: 18758,
  ran_at: '2026-11-04T08:34:04+00:00',
}

afterEach(() => clearLabResults())

describe('labResults', () => {
  it('drops a stored preview result on load, since jobs no longer preview', async () => {
    sessionStorage.setItem(
      'mb-lab-results',
      JSON.stringify({
        consolidate: {
          request: { scope: RUN.scope, action: 'consolidate', dry_run: true },
          run: RUN,
        },
        elaborate: {
          request: { scope: RUN.scope, action: 'elaborate', dry_run: false },
          run: { ...RUN, action: 'elaborate' },
        },
      }),
    )

    vi.resetModules()
    const { getLabResults } = await import('@/components/admin/labResults')

    expect(Object.keys(getLabResults())).toEqual(['elaborate'])
  })
})
