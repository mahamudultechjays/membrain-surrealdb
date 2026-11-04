import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { Me } from '@/api/auth'
import type { BrainApi, BrainResponse } from '@/api/brain'
import BrainPage from '@/pages/BrainPage'

const MINE = 'org/spreetail/user/arun_das'
const VIDYUL = 'org/spreetail/user/vidyul'

const ME: Me = {
  email: 'arun.das@spreetail.com',
  name: 'Arun Das',
  is_admin: false,
  grants: [
    { scope_path: MINE, access: 'write', layer: 'personal', owner: 'Arun Das' },
    { scope_path: VIDYUL, access: 'read', layer: 'team', owner: 'Vidyul Narayanan' },
  ],
}

const RESPONSE: BrainResponse = {
  entities: [
    {
      ref: 'concept/tier_a',
      name: 'Tier A products',
      entity_type: 'concept',
      category: 'knowledge',
      scopes: [MINE],
      updated_at: '2026-11-03T10:00:00+00:00',
      facts: [
        {
          id: 'f1',
          key: 'pre_build_weeks',
          value: '4-5',
          category: 'context',
          scopes: [MINE],
          created_at: '2026-11-03T10:00:00+00:00',
          replaced: false,
          summary: 'Tier A products need a 4-5 week pre-build',
          labels: ['source=email', 'season=q4'],
        },
      ],
      relations: [
        {
          id: 'r1',
          label: 'managed_by',
          object_ref: 'organisation/spreetail',
          object_name: 'Spreetail',
          category: 'context',
          scopes: [MINE],
          created_at: '2026-11-03T10:01:00+00:00',
          summary: null,
          labels: [],
        },
      ],
    },
    {
      ref: 'organisation/acme',
      name: 'Acme Logistics',
      entity_type: 'organisation',
      category: 'knowledge',
      scopes: [VIDYUL],
      updated_at: '2026-10-20T09:00:00+00:00',
      facts: [
        {
          id: 'f2',
          key: 'lead_time',
          value: '18 days',
          category: 'knowledge',
          scopes: [VIDYUL],
          created_at: '2026-10-20T09:00:00+00:00',
          replaced: false,
          summary: null,
          labels: [],
        },
      ],
      relations: [],
    },
  ],
  scopes: [MINE, VIDYUL],
  total_facts: 2,
  total_relations: 1,
}

function fakeApi(): BrainApi {
  return { list: vi.fn<BrainApi['list']>(async () => RESPONSE) }
}

describe('BrainPage', () => {
  it('lists every fact as its own row, and opens one to show its details', async () => {
    render(<BrainPage me={ME} api={fakeApi()} />)

    const row = await screen.findByRole('button', { name: /pre_build_weeks/ })
    expect(screen.getByText('3 facts')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /Tier A products/ })).toHaveLength(2)
    expect(row).toHaveAttribute('aria-expanded', 'false')

    fireEvent.click(row)
    expect(row).toHaveAttribute('aria-expanded', 'true')
    const details = document.getElementById(row.getAttribute('aria-controls')!)!
    expect(within(details).getByText('Tier A products')).toBeInTheDocument()
    expect(within(details).getByText('context')).toBeInTheDocument()
    expect(within(details).getByText(MINE)).toBeInTheDocument()
    expect(
      within(details).getByText('Tier A products need a 4-5 week pre-build'),
    ).toBeInTheDocument()
    expect(within(details).getByText('season=q4')).toBeInTheDocument()

    // One row open at a time; a relation with no summary or labels shows a dash.
    const relation = screen.getByRole('button', { name: /managed_by/ })
    fireEvent.click(relation)
    expect(row).toHaveAttribute('aria-expanded', 'false')
    const relationDetails = document.getElementById(
      relation.getAttribute('aria-controls')!,
    )!
    const field = (name: string) =>
      within(relationDetails).getByText(name).nextElementSibling?.textContent
    expect(field('Summary')).toBe('—')
    expect(field('Labels')).toBe('—')
    expect(field('Confidence')).toBe('—')
    expect(field('Related ref')).toBe('organisation/spreetail')
    expect(field('ID')).toBe('r1')
  })

  it('filters by kind, entity type and search, and can clear them', async () => {
    render(<BrainPage me={ME} api={fakeApi()} />)
    await screen.findByRole('button', { name: /pre_build_weeks/ })

    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'relation' } })
    expect(screen.getByText('1 fact of 3')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /managed_by/ })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    fireEvent.change(screen.getByLabelText('Entity type'), {
      target: { value: 'organisation' },
    })
    expect(
      screen.queryByRole('button', { name: /pre_build_weeks/ }),
    ).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /lead_time/ })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    fireEvent.change(screen.getByLabelText('Search'), {
      target: { value: 'nothing like it' },
    })
    expect(screen.getByText('Nothing matches these filters.')).toBeInTheDocument()
  })

  it('names spaces by whose they are, and asks the backend for only the ticked ones', async () => {
    const api = fakeApi()
    render(<BrainPage me={ME} api={api} />)
    await screen.findByRole('button', { name: /pre_build_weeks/ })
    expect(api.list).toHaveBeenLastCalledWith(
      { scopes: [], subscopes: false },
      expect.any(AbortSignal),
    )

    fireEvent.click(screen.getByRole('button', { name: 'Spaces: All spaces' }))
    expect(screen.getByRole('checkbox', { name: /My space/ })).toBeChecked()
    fireEvent.click(screen.getByRole('checkbox', { name: /Vidyul Narayanan/ }))

    await waitFor(() =>
      expect(api.list).toHaveBeenLastCalledWith(
        { scopes: [MINE], subscopes: false },
        expect.any(AbortSignal),
      ),
    )
    fireEvent.click(screen.getByLabelText('Include sub-spaces'))
    await waitFor(() =>
      expect(api.list).toHaveBeenLastCalledWith(
        { scopes: [MINE], subscopes: true },
        expect.any(AbortSignal),
      ),
    )
  })

  it('asks for nothing when every space is deselected', async () => {
    const api = fakeApi()
    render(<BrainPage me={ME} api={api} />)
    await screen.findByRole('button', { name: /pre_build_weeks/ })
    const calls = vi.mocked(api.list).mock.calls.length

    fireEvent.click(screen.getByRole('button', { name: 'Spaces: All spaces' }))
    fireEvent.click(screen.getByRole('button', { name: 'Deselect all' }))

    expect(screen.getByText(/No spaces selected/)).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /pre_build_weeks/ }),
    ).not.toBeInTheDocument()
    // No request: an empty scope list would mean "everything" to the backend.
    expect(api.list).toHaveBeenCalledTimes(calls)
  })

  it("shows the backend's reason when it can't load", async () => {
    const api: BrainApi = {
      list: vi.fn<BrainApi['list']>(async () => {
        throw new Error('Agent Memory call failed: timeout')
      }),
    }
    render(<BrainPage me={ME} api={api} />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Agent Memory call failed')
  })
})
