import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { Me } from '@/api/auth'
import type { BrainApi, BrainResponse } from '@/api/brain'
import type { BrainRow } from '@/components/brain/filter'
import BrainPage from '@/pages/BrainPage'

// The real graph needs WebGL; BrainGraph has its own tests.
vi.mock('@/components/brain/graph/BrainGraph', () => ({
  default: ({ rows, onOpen }: { rows: BrainRow[]; onOpen: (id: string) => void }) => (
    <div>
      graph of {rows.length} rows
      <button type="button" onClick={() => onOpen('fact:f1')}>
        open f1
      </button>
    </div>
  ),
}))

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
          source: { kind: 'turn', ref: 'turn:t1', session_id: 's1', trust: 0.5 },
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
  chunks: [
    {
      id: 't1',
      session_id: 's1',
      role: 'user',
      text: 'Pre-build for tier A takes 4-5 weeks.\nPlan Q4 around it.',
      created_at: '2026-11-03T09:59:00+00:00',
      scopes: [MINE],
      derived: ['f1'],
    },
  ],
  total_chunks: 1,
  chunks_missing: 0,
  actions: [],
  unknowns: [],
  replaced_loaded: false,
  replaced_missing: 0,
}

function fakeApi(response: BrainResponse = RESPONSE): BrainApi {
  return { list: vi.fn<BrainApi['list']>(async () => response) }
}

describe('BrainPage', () => {
  it('lists every fact as its own row, and opens one to show its details', async () => {
    render(<BrainPage me={ME} api={fakeApi()} />)

    const row = await screen.findByRole('button', { name: /pre_build_weeks/ })
    expect(screen.getByText('4 records')).toBeInTheDocument()
    expect(screen.getByLabelText('Show')).toHaveValue('all')
    expect(screen.getByRole('option', { name: 'Memory chunks (1)' })).toBeInTheDocument()
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
    expect(screen.getByText('1 relation')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /managed_by/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /lead_time/ })).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'all' } })

    // A chip shows its choice and stands out while it narrows the list.
    const type = screen.getByLabelText('Entity type')
    fireEvent.change(type, { target: { value: 'organisation' } })
    expect(type.closest('.brain-chip')).toHaveAttribute('data-active')
    expect(type.closest('.brain-chip')).toHaveTextContent('Typeorganisation')
    expect(
      screen.queryByRole('button', { name: /pre_build_weeks/ }),
    ).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /lead_time/ })).toBeInTheDocument()
    // Counts on the kind switch follow the other filters.
    expect(screen.getByRole('option', { name: 'Facts (1)' })).toBeInTheDocument()
    expect(screen.getByText('of 4', { exact: false })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(type.closest('.brain-chip')).not.toHaveAttribute('data-active')
    fireEvent.change(screen.getByLabelText('Search'), {
      target: { value: 'nothing like it' },
    })
    expect(screen.getByText('Nothing matches these filters.')).toBeInTheDocument()
  })

  it('lists memory chunks, linked both ways to the facts taken from them', async () => {
    render(<BrainPage me={ME} api={fakeApi()} />)
    await screen.findByRole('button', { name: /pre_build_weeks/ })

    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'chunk' } })
    expect(screen.getByText('1 memory chunk')).toBeInTheDocument()
    // Replaced values don't apply to chunks, so that chip goes.
    expect(screen.queryByLabelText('Old values')).not.toBeInTheDocument()
    const chunk = screen.getByRole('button', { name: /Pre-build for tier A/ })
    fireEvent.click(chunk)
    const details = document.getElementById(chunk.getAttribute('aria-controls')!)!
    expect(within(details).getByText(/Plan Q4 around it/)).toBeInTheDocument()
    expect(within(details).getByText('s1')).toBeInTheDocument()

    // The fact is hidden under "Memory chunks": following it widens the filters.
    fireEvent.click(
      within(details).getByRole('button', { name: /pre_build_weeks = 4-5/ }),
    )
    expect(screen.getByLabelText('Show')).toHaveValue('all')
    const fact = screen.getByRole('button', { name: /pre_build_weeks/ })
    expect(fact).toHaveAttribute('aria-expanded', 'true')
    expect(fact).toHaveFocus()

    const factDetails = document.getElementById(fact.getAttribute('aria-controls')!)!
    fireEvent.click(
      within(factDetails).getByRole('button', { name: 'Show the memory chunk' }),
    )
    expect(screen.getByRole('button', { name: /Pre-build for tier A/ })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
  })

  it('#/brain/graph draws the filtered rows as a graph, and opens a node’s row in the list', async () => {
    window.location.hash = '#/brain/graph'
    try {
      render(<BrainPage me={ME} api={fakeApi()} />)

      expect(await screen.findByText('graph of 4 rows')).toBeInTheDocument()
      const views = screen.getByRole('navigation', { name: 'Brain view' })
      expect(within(views).getByRole('link', { name: 'Graph' })).toHaveAttribute(
        'aria-current',
        'page',
      )
      // Order means nothing on a graph; the filters still apply.
      expect(screen.queryByLabelText('Sort')).not.toBeInTheDocument()
      fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'fact' } })
      expect(screen.getByText('graph of 2 rows')).toBeInTheDocument()

      fireEvent.click(screen.getByRole('button', { name: 'open f1' }))
      const row = await screen.findByRole('button', { name: /pre_build_weeks/ })
      expect(row).toHaveAttribute('aria-expanded', 'true')
      expect(window.location.hash).toBe('#/brain/list')
    } finally {
      window.location.hash = ''
    }
  })

  it('renders a long list a page at a time', async () => {
    const [first] = RESPONSE.entities
    const facts = Array.from({ length: 160 }, (_, i) => ({
      ...first!.facts[0]!,
      id: `bulk${i}`,
      key: `bulk_fact_${String(i).padStart(3, '0')}`,
      source: undefined,
    }))
    const big: BrainResponse = {
      ...RESPONSE,
      entities: [{ ...first!, facts, relations: [] }],
      chunks: [],
    }
    render(<BrainPage me={ME} api={fakeApi(big)} />)
    await screen.findByRole('button', { name: /bulk_fact_000/ })

    // Counted by row, not by role: role queries over hundreds of buttons are slow.
    const rowCount = () => document.querySelectorAll('.brain-list > li').length
    expect(rowCount()).toBe(150)
    expect(screen.getByText('Showing 150 of 160')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show 10 more' }))
    expect(rowCount()).toBe(160)
    expect(screen.queryByText(/^Showing/)).not.toBeInTheDocument()
  })

  it('"/" jumps to the search box', async () => {
    render(<BrainPage me={ME} api={fakeApi()} />)
    await screen.findByRole('button', { name: /pre_build_weeks/ })

    fireEvent.keyDown(document.body, { key: '/' })
    expect(screen.getByLabelText('Search')).toHaveFocus()
    // Typed inside a field, "/" is just a character.
    const event = fireEvent.keyDown(screen.getByLabelText('Search'), { key: '/' })
    expect(event).toBe(true)
  })

  it('offers the next step when the user’s space is empty', async () => {
    const api = fakeApi({ ...RESPONSE, entities: [], chunks: [] })
    render(<BrainPage me={ME} api={api} />)

    expect(
      await screen.findByText('Nothing saved in your space yet.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Capture something' })).toHaveAttribute(
      'href',
      '#/capture',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Look in all spaces' }))
    await waitFor(() =>
      expect(api.list).toHaveBeenLastCalledWith(
        { scopes: [], subscopes: true, replaced: false },
        expect.any(AbortSignal),
      ),
    )
  })

  it('lists actions and unknowns as their own kinds, each opening to its details', async () => {
    const api = fakeApi({
      ...RESPONSE,
      actions: [
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
          scopes: [MINE],
          source: { kind: 'turn', ref: 'turn:t1', session_id: 's1', trust: 0.5 },
        },
      ],
      unknowns: [
        {
          id: 'u1',
          about: 'It is late again.',
          reason: "'It' is ambiguous",
          resolved: false,
          resolvable: false,
          entity_ref: 'organisation/acme',
          entity_name: 'Acme Logistics',
          key: 'lead_time',
          scopes: [MINE],
          labels: [],
          created_at: '2026-11-03T11:30:00+00:00',
        },
      ],
    })
    render(<BrainPage me={ME} api={api} />)
    await screen.findByRole('button', { name: /pre_build_weeks/ })

    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'action' } })
    const action = screen.getByRole('button', { name: /delayed/ })
    fireEvent.click(action)
    const actionDetails = document.getElementById(action.getAttribute('aria-controls')!)!
    expect(
      within(actionDetails).getByText('Acme delayed the Reno shipment'),
    ).toBeVisible()
    // Captured from t1, which is loaded as a chunk: the link goes there.
    expect(
      within(actionDetails).getByRole('button', { name: 'Show the memory chunk' }),
    ).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Show'), { target: { value: 'unknown' } })
    const unknown = screen.getByRole('button', { name: /It is late again/ })
    expect(unknown).toHaveTextContent('open')
    fireEvent.click(unknown)
    const unknownDetails = document.getElementById(
      unknown.getAttribute('aria-controls')!,
    )!
    expect(within(unknownDetails).getByText("'It' is ambiguous")).toBeVisible()
    expect(
      within(unknownDetails).getByText('Open: memory can’t settle this by itself'),
    ).toBeVisible()
  })

  it('asks for old values only when they are wanted', async () => {
    const api = fakeApi()
    render(<BrainPage me={ME} api={api} />)
    await screen.findByRole('button', { name: /pre_build_weeks/ })

    fireEvent.click(screen.getByLabelText('Old values'))
    await waitFor(() =>
      expect(api.list).toHaveBeenLastCalledWith(
        { scopes: [MINE], subscopes: true, replaced: true },
        expect.any(AbortSignal),
      ),
    )
  })

  it('says when some memory chunks could not be read', async () => {
    render(<BrainPage me={ME} api={fakeApi({ ...RESPONSE, chunks_missing: 2 })} />)

    expect(await screen.findByRole('status')).toHaveTextContent(
      "The text of 2 captures couldn't be read this time",
    )
  })

  it('names spaces by whose they are, and asks the backend for only the ticked ones', async () => {
    const api = fakeApi()
    render(<BrainPage me={ME} api={api} />)
    await screen.findByRole('button', { name: /pre_build_weeks/ })
    // It opens on the user's own space alone.
    expect(api.list).toHaveBeenCalledTimes(1)
    expect(api.list).toHaveBeenLastCalledWith(
      { scopes: [MINE], subscopes: true, replaced: false },
      expect.any(AbortSignal),
    )

    fireEvent.click(screen.getByRole('button', { name: 'Spaces: My space' }))
    expect(screen.getByRole('checkbox', { name: /My space/ })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: /Vidyul Narayanan/ })).not.toBeChecked()

    // Ticking the rest is "everything": no narrowing sent.
    fireEvent.click(screen.getByRole('checkbox', { name: /Vidyul Narayanan/ }))
    await waitFor(() =>
      expect(api.list).toHaveBeenLastCalledWith(
        { scopes: [], subscopes: true, replaced: false },
        expect.any(AbortSignal),
      ),
    )
    fireEvent.click(screen.getByRole('checkbox', { name: /Vidyul Narayanan/ }))
    await waitFor(() =>
      expect(api.list).toHaveBeenLastCalledWith(
        { scopes: [MINE], subscopes: true, replaced: false },
        expect.any(AbortSignal),
      ),
    )
    // Sub-spaces show by default; ticking Exclude leaves them out.
    expect(screen.getByLabelText('Exclude sub-spaces')).not.toBeChecked()
    fireEvent.click(screen.getByLabelText('Exclude sub-spaces'))
    await waitFor(() =>
      expect(api.list).toHaveBeenLastCalledWith(
        { scopes: [MINE], subscopes: false, replaced: false },
        expect.any(AbortSignal),
      ),
    )
  })

  it('asks for nothing when every space is deselected', async () => {
    const api = fakeApi()
    render(<BrainPage me={ME} api={api} />)
    await screen.findByRole('button', { name: /pre_build_weeks/ })
    const calls = vi.mocked(api.list).mock.calls.length

    fireEvent.click(screen.getByRole('button', { name: /^Spaces:/ }))
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
