import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ApiError } from '@/api/client'
import type { LabApi, LabRun, LabRunRequest } from '@/api/lab'
import MemoryLab from '@/components/admin/MemoryLab'
import { clearLabResults } from '@/components/admin/labResults'

const ORG = 'org/spreetail'
const MINE = 'org/spreetail/user/vidyul_narayanan'

afterEach(() => clearLabResults())

function result(request: LabRunRequest): LabRun {
  return {
    action: request.action,
    scope: request.scope,
    before: { entities: 3, attributes: 9, relations: 2, by_source: { turn: 11 } },
    after: {
      entities: 3,
      attributes: 11,
      relations: 2,
      by_source: { turn: 11, consolidation: 2 },
    },
    outcome: {
      summary: { created: 2, updated: 0, superseded: 0 },
      items: ['create · Acme · lead_time = 18 days (proof 2)'],
      text: request.action === 'reflect' ? 'Acme is the only carrier.' : null,
      trace_ids: ['tr-1'],
    },
    latency_ms: 4200,
    ran_at: '2026-11-04T08:00:00+00:00',
  }
}

function fakeApi() {
  const runs: LabRunRequest[] = []
  let failNext: Error | null = null
  const api: LabApi = {
    scopes: () => Promise.resolve([ORG, MINE]),
    run: (request) => {
      runs.push(request)
      if (failNext) {
        const error = failNext
        failNext = null
        return Promise.reject(error)
      }
      return Promise.resolve(result(request))
    },
  }
  return { api, runs, fail: (e: Error) => (failNext = e) }
}

async function renderJobs(api: LabApi) {
  render(<MemoryLab api={api} />)
  await within(job('Consolidate')).findByRole('option', { name: MINE })
}

const job = (name: string) => screen.getByRole('region', { name })

/** Each job has its own scope picker, next to its button. */
const pickScope = (jobName: string, value: string) =>
  fireEvent.change(within(job(jobName)).getByLabelText('Scope'), { target: { value } })

describe('Memory jobs', () => {
  it('runs a job on the chosen scope and shows what it did under its button', async () => {
    const { api, runs } = fakeApi()
    await renderJobs(api)
    pickScope('Consolidate', MINE)

    fireEvent.click(screen.getByRole('button', { name: 'Consolidate' }))

    const panel = await within(job('Consolidate')).findByRole('group', { name: /Result/ })
    expect(runs).toEqual([{ scope: MINE, action: 'consolidate', dry_run: false }])
    expect(panel).toHaveAttribute('open')
    expect(panel).toHaveTextContent('created 2')
    expect(panel).toHaveTextContent('attributes 9 → 11')
    expect(panel).toHaveTextContent('+2 consolidation')
    expect(panel).toHaveTextContent('create · Acme · lead_time = 18 days (proof 2)')
    expect(within(job('Elaborate')).queryByRole('group')).not.toBeInTheDocument()
  })

  it('a click runs the job for real: there is no preview option', async () => {
    const { api, runs } = fakeApi()
    await renderJobs(api)

    expect(screen.queryByRole('checkbox', { name: 'Preview' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Elaborate' }))

    const panel = await within(job('Elaborate')).findByRole('group', { name: /Result/ })
    expect(runs).toEqual([{ scope: ORG, action: 'elaborate', dry_run: false }])
    expect(panel).toHaveTextContent('Saved')
  })

  it('reflects on a question, optionally saving, and shows the synthesis', async () => {
    const { api, runs } = fakeApi()
    await renderJobs(api)
    expect(screen.getByRole('button', { name: 'Reflect' })).toBeDisabled()

    fireEvent.change(screen.getByLabelText('Question'), {
      target: { value: 'What do we know about carriers?' },
    })
    fireEvent.click(screen.getByRole('checkbox', { name: 'Save insights as facts' }))
    fireEvent.click(screen.getByRole('button', { name: 'Reflect' }))

    const panel = await within(job('Reflect')).findByRole('group', { name: /Result/ })
    expect(runs).toEqual([
      {
        scope: ORG,
        action: 'reflect',
        query: 'What do we know about carriers?',
        persist: true,
      },
    ])
    expect(panel).toHaveTextContent('Acme is the only carrier.')
  })

  it('pickers offer only real scopes, never the whole context', async () => {
    const { api } = fakeApi()
    await renderJobs(api)

    for (const name of ['Consolidate', 'Elaborate', 'Reflect']) {
      const options = within(job(name))
        .getAllByRole('option')
        .map((o) => o.textContent)
      expect(options).toEqual([ORG, MINE])
    }
  })

  it('each job runs on its own scope', async () => {
    const { api, runs } = fakeApi()
    await renderJobs(api)
    pickScope('Consolidate', MINE)
    pickScope('Elaborate', ORG)
    pickScope('Reflect', MINE)
    fireEvent.change(screen.getByLabelText('Question'), {
      target: { value: 'Carriers?' },
    })

    fireEvent.click(screen.getByRole('button', { name: 'Consolidate' }))
    await within(job('Consolidate')).findByRole('group', { name: /Result/ })
    fireEvent.click(screen.getByRole('button', { name: 'Elaborate' }))
    await within(job('Elaborate')).findByRole('group', { name: /Result/ })
    fireEvent.click(screen.getByRole('button', { name: 'Reflect' }))
    await within(job('Reflect')).findByRole('group', { name: /Result/ })

    expect(runs.map((r) => [r.action, r.scope])).toEqual([
      ['consolidate', MINE],
      ['elaborate', ORG],
      ['reflect', MINE],
    ])
  })

  it('shows a failure under the job that failed', async () => {
    const { api, fail } = fakeApi()
    await renderJobs(api)
    fail(new ApiError(503, 'Agent Memory call failed: timeout'))

    fireEvent.click(screen.getByRole('button', { name: 'Consolidate' }))

    expect(await within(job('Consolidate')).findByRole('alert')).toHaveTextContent(
      'Agent Memory call failed: timeout',
    )
  })

  it('a new run replaces that job’s result, and results survive leaving the page', async () => {
    const { api, runs } = fakeApi()
    const first = render(<MemoryLab api={api} />)
    await within(job('Consolidate')).findByRole('option', { name: MINE })
    fireEvent.click(screen.getByRole('button', { name: 'Consolidate' }))
    await within(job('Consolidate')).findByRole('group', { name: /Result/ })
    fireEvent.click(screen.getByRole('button', { name: 'Consolidate' }))
    await waitFor(() => expect(runs).toHaveLength(2))

    first.unmount()
    await renderJobs(api)

    expect(
      within(job('Consolidate')).getAllByRole('group', { name: /Result/ }),
    ).toHaveLength(1)
  })
})
