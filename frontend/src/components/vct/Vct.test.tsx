import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { AskResponse } from '@/api/ask'
import { ApiError } from '@/api/client'
import type {
  FactTagDetail,
  FactTags,
  TagRef,
  TaggerStatus,
  VctApi,
  VctMap,
  VctNode,
} from '@/api/vct'
import AskAnswer from '@/components/ask/AskAnswer'
import {
  OnboardUser,
  TagEditor,
  TaggerPanel,
  VctCoverageView,
  VctFilterBar,
  VctTags,
} from '@/components/vct/Vct'
import { NO_VCT_FILTER, resetVctMapCache } from '@/components/vct/vctState'

const node = (id: string, name: string, domain: string, section: string): VctNode => ({
  id,
  name,
  description: '',
  domain_id: domain,
  section_id: section,
})

const SC6 = node('sc6', 'Select Transport', 'supply-chain', 'fulfillment')
const SC4 = node('sc4', 'Store Inventory', 'supply-chain', 'fulfillment')
const FI4 = node('fi4', 'Manage Cash & Payouts', 'finance', 'post-sale')

const MAP: VctMap = {
  topology_version: 'test',
  domains: [
    { id: 'supply-chain', name: 'Supply Chain', nodes: [SC6, SC4] },
    { id: 'finance', name: 'Finance', nodes: [FI4] },
  ],
  sections: [
    {
      id: 'fulfillment',
      label: 'Fulfil',
      ebitda_weight: 0.3,
      goals: [
        { id: 'ff-mgmt5', name: 'Carrier & Freight Cost', description: '', weight: 0.05 },
      ],
    },
    {
      id: 'post-sale',
      label: 'Post-sale',
      ebitda_weight: 0.1,
      goals: [{ id: 'ps-mgmt5', name: 'Payout Timing', description: '', weight: 0.02 }],
    },
  ],
}

function ref(
  kind: 'node' | 'goal',
  id: string,
  name: string,
  rank = 1,
  source: 'auto' | 'user' = 'auto',
): TagRef {
  return { kind, id, name, section_id: 'fulfillment', section: 'Fulfil', source, rank }
}

const TRANSPORT = ref('node', 'sc6', 'Select Transport')
const FREIGHT = ref('goal', 'ff-mgmt5', 'Carrier & Freight Cost')

const DETAIL: FactTagDetail = {
  fact_id: 'f1',
  scope: 'org/spreetail/user/mahamudul_hasan',
  business: true,
  tagged_at: '2026-11-09T06:00:00+00:00',
  reviewed_at: null,
  reviewed_by: null,
  guess_nodes: [],
  guess_goals: [],
  nodes: [TRANSPORT, ref('node', 'fi4', 'Manage Cash & Payouts', 2)],
  goals: [FREIGHT],
}

const STATUS: TaggerStatus = {
  enabled: true,
  version: 'v1',
  scopes: ['org/spreetail/user/mahamudul_hasan'],
  interval_hours: 3,
  running: false,
  next_run_at: '2026-11-06T15:00:00+00:00',
  current: null,
  last: {
    started_at: '2026-11-06T12:00:00+00:00',
    finished_at: '2026-11-06T12:01:00+00:00',
    scopes: ['org/spreetail/user/mahamudul_hasan'],
    listed: 6,
    new: 6,
    tagged: 6,
    not_business: 2,
    carried: 0,
    failed: 0,
    capped: false,
    error: null,
  },
  tagged_facts: 6,
  not_business: 2,
  stats: {
    days: 7,
    edits: 4,
    corrections: 1,
    correction_rate: 0.25,
    confusions: [{ old: 'mo1', new: 'fi4', times: 1 }],
  },
}

function fakeApi(overrides: Partial<VctApi> = {}): VctApi {
  return {
    map: vi.fn<VctApi['map']>().mockResolvedValue(MAP),
    factTags: vi.fn<VctApi['factTags']>().mockResolvedValue(DETAIL),
    editTag: vi.fn<VctApi['editTag']>().mockImplementation((_id, edit) =>
      Promise.resolve({
        ...DETAIL,
        nodes:
          edit.kind === 'node' && edit.tag
            ? [ref('node', edit.tag, 'Manage Cash & Payouts', 1, 'user')]
            : DETAIL.nodes,
      }),
    ),
    reviewFacts: vi
      .fn<VctApi['reviewFacts']>()
      .mockImplementation((ids) => Promise.resolve({ done: ids, skipped: [] })),
    coverage: vi.fn<VctApi['coverage']>().mockResolvedValue({
      scopes: ['org/spreetail'],
      tagged_facts: 3,
      without_goal: 1,
      not_business: 1,
      nodes: [{ id: 'sc6', facts: 2 }],
      goals: [{ id: 'ff-mgmt5', facts: 2 }],
      cells: [
        { domain_id: 'supply-chain', section_id: 'fulfillment', nodes: 2, facts: 2 },
        { domain_id: 'finance', section_id: 'post-sale', nodes: 1, facts: 0 },
      ],
    }),
    tagger: vi.fn<VctApi['tagger']>().mockResolvedValue(STATUS),
    runTagger: vi
      .fn<VctApi['runTagger']>()
      .mockResolvedValue({ ...STATUS, running: true }),
    previewOnboarding: vi.fn<VctApi['previewOnboarding']>().mockResolvedValue({
      clauses: [{ clause: 'I pick carriers', candidates: [SC6, SC4] }],
      suggested: ['sc6'],
      domains: [{ id: 'supply-chain', name: 'Supply Chain' }],
    }),
    myOnboarding: vi.fn<VctApi['myOnboarding']>().mockResolvedValue({
      email: 'priya@x.com',
      onboarded: true,
      primary_work: 'I pick carriers',
      nodes: [{ ...SC6, rank: 1, is_primary: true, confirmed_by: 'user' }],
      domains: [{ id: 'supply-chain', name: 'Supply Chain' }],
    }),
    userOnboarding: vi
      .fn<VctApi['userOnboarding']>()
      .mockRejectedValue(new ApiError(404, 'none')),
    setUserNodes: vi.fn<VctApi['setUserNodes']>().mockImplementation((email) =>
      Promise.resolve({
        email,
        onboarded: true,
        primary_work: '',
        nodes: [],
        domains: [{ id: 'supply-chain', name: 'Supply Chain' }],
      }),
    ),
    ...overrides,
  }
}

afterEach(() => resetVctMapCache())

describe('VctTags', () => {
  it('shows the node and goal, and a pending note before the tagger ran', () => {
    const confirmed = { ...FREIGHT, source: 'user' as const }
    const { rerender } = render(<VctTags tags={{ node: TRANSPORT, goal: confirmed }} />)
    expect(screen.getByText('Select Transport')).toBeInTheDocument()
    expect(
      screen.getByText('Carrier & Freight Cost').closest('[data-source]'),
    ).toHaveAttribute('data-source', 'user')

    rerender(<VctTags tags={null} tagged={false} />)
    expect(screen.getByText('tagging within 3 h')).toBeInTheDocument()

    rerender(<VctTags tags={null} />)
    expect(screen.queryByText('tagging within 3 h')).not.toBeInTheDocument()

    rerender(<VctTags tags={null} business={false} />)
    expect(screen.getByText('not business')).toBeInTheDocument()
  })
})

describe('TagEditor', () => {
  it('picks an alternative, confirms and removes, and reports the new tags', async () => {
    const api = fakeApi()
    const onChange = vi.fn<(tags: FactTags | null) => void>()
    render(<TagEditor factId="attribute:f1" api={api} onChange={onChange} />)

    fireEvent.click(await screen.findByRole('button', { name: /fi4 Manage Cash/ }))
    await waitFor(() =>
      expect(api.editTag).toHaveBeenCalledWith('attribute:f1', {
        kind: 'node',
        action: 'change',
        tag: 'fi4',
      }),
    )
    await waitFor(() => expect(onChange).toHaveBeenCalled())
    expect(onChange.mock.calls[0]![0]?.node?.id).toBe('fi4')

    fireEvent.click(await screen.findByRole('button', { name: 'Confirm goal' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Remove goal' }))
    await waitFor(() => expect(api.editTag).toHaveBeenCalledTimes(3))
    expect(api.editTag).toHaveBeenCalledWith('attribute:f1', {
      kind: 'goal',
      action: 'accept',
    })
  })

  it('chooses any goal from the map', async () => {
    const api = fakeApi()
    render(<TagEditor factId="f1" api={api} />)

    const pick = await screen.findByLabelText('Choose another goal')
    await waitFor(() => expect(pick).not.toBeDisabled())
    fireEvent.change(pick, { target: { value: 'ps-mgmt5' } })

    await waitFor(() =>
      expect(api.editTag).toHaveBeenCalledWith('f1', {
        kind: 'goal',
        action: 'change',
        tag: 'ps-mgmt5',
      }),
    )
  })

  it('says when the fact is not tagged yet, and shows errors', async () => {
    const missing = fakeApi({
      factTags: vi.fn<VctApi['factTags']>().mockRejectedValue(new ApiError(404, 'no')),
    })
    const { unmount } = render(<TagEditor factId="f9" api={missing} />)
    expect(await screen.findByText(/Not tagged yet/)).toBeInTheDocument()
    unmount()

    const broken = fakeApi({
      factTags: vi.fn<VctApi['factTags']>().mockRejectedValue(new ApiError(403, 'Nope')),
    })
    render(<TagEditor factId="f9" api={broken} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Nope')
  })
})

describe('VctFilterBar', () => {
  it('adds and removes values, and offers the user their own domains or nodes', async () => {
    const onChange = vi.fn<(value: unknown) => void>()
    const api = fakeApi()
    const mine = await api.myOnboarding()
    const { rerender } = render(
      <VctFilterBar value={NO_VCT_FILTER} onChange={onChange} api={api} />,
    )
    const goal = screen.getByLabelText('Goal')
    await waitFor(() => expect(goal).not.toBeDisabled())
    expect(screen.getByText(/not mapped to the value chain yet/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'My domains' })).not.toBeInTheDocument()

    fireEvent.change(goal, { target: { value: 'ff-mgmt5' } })
    expect(onChange).toHaveBeenCalledWith({ goals: ['ff-mgmt5'], nodes: [], domains: [] })

    rerender(
      <VctFilterBar
        value={{ goals: ['ff-mgmt5'], nodes: [], domains: ['finance'] }}
        onChange={onChange}
        mine={mine}
        api={api}
      />,
    )
    fireEvent.click(
      screen.getByRole('button', { name: 'Remove goal Carrier & Freight Cost' }),
    )
    expect(onChange).toHaveBeenLastCalledWith({
      goals: [],
      nodes: [],
      domains: ['finance'],
    })
    fireEvent.click(screen.getByRole('button', { name: 'My domains' }))
    expect(onChange).toHaveBeenLastCalledWith({
      goals: [],
      nodes: [],
      domains: ['supply-chain'],
    })
    fireEvent.click(screen.getByRole('button', { name: 'Only my nodes' }))
    expect(onChange).toHaveBeenLastCalledWith({ goals: [], nodes: ['sc6'], domains: [] })
    fireEvent.click(screen.getByRole('button', { name: 'Clear' }))
    expect(onChange).toHaveBeenLastCalledWith(NO_VCT_FILTER)

    // Mapped to domains but no nodes: no "no nodes" text, and only My domains.
    rerender(
      <VctFilterBar
        value={{ goals: [], nodes: [], domains: ['supply-chain'] }}
        onChange={onChange}
        mine={{ ...mine, nodes: [] }}
        api={api}
      />,
    )
    expect(screen.getByText(/Starts on your value chain domains/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'My domains' })).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'Only my nodes' }),
    ).not.toBeInTheDocument()
  })
})

describe('AskAnswer', () => {
  const fact = (id: string, text: string) => ({
    fact: text,
    source: {
      kind: 'memory' as const,
      hit_kind: 'attribute',
      hit_id: id,
      title: null,
      date: null,
      text,
      score: 0.3,
    },
    tags: { node: TRANSPORT, goal: FREIGHT },
  })
  const answer: AskResponse = {
    q: 'Why is freight up?',
    scopes: ['org/spreetail'],
    answered_at: 'now',
    facts: [
      fact('attribute:f1', 'UPS rate up 5.9%'),
      { ...fact('attribute:f2', 'Team lunch is Friday'), tags: null },
    ],
    value_facts: [fact('attribute:f1', 'UPS rate up 5.9%')],
    metadata: {
      total_facts: 2,
      resolution_tier: 'hybrid',
      latency_ms: 10,
      include_inferred: false,
      trace_ids: [],
      filter: { goals: [], nodes: [], domains: ['supply-chain'], removed: 1 },
    },
    trace_id: null,
  }

  it('shows every result in Normal and only the matches in Value-driven', () => {
    render(<AskAnswer answer={answer} who="Priya" />)

    const normal = screen.getByRole('region', { name: 'Normal' })
    const valueDriven = screen.getByRole('region', { name: 'Value-driven' })
    expect(within(normal).getByText('UPS rate up 5.9%')).toBeInTheDocument()
    expect(within(normal).getByText('Team lunch is Friday')).toBeInTheDocument()
    expect(within(valueDriven).getByText('UPS rate up 5.9%')).toBeInTheDocument()
    expect(
      within(valueDriven).queryByText('Team lunch is Friday'),
    ).not.toBeInTheDocument()
    expect(
      within(valueDriven).getByText(/supply-chain · 1 result left out/),
    ).toBeInTheDocument()
    expect(within(valueDriven).getByText('Select Transport')).toBeInTheDocument()
  })

  it('asks for a filter when there is none', () => {
    render(
      <AskAnswer
        answer={{
          ...answer,
          value_facts: null,
          metadata: { ...answer.metadata, filter: null },
        }}
        who="Priya"
      />,
    )

    const valueDriven = screen.getByRole('region', { name: 'Value-driven' })
    expect(
      within(valueDriven).getByText(/Pick a domain, node or goal/),
    ).toBeInTheDocument()
  })
})

describe('VctCoverageView', () => {
  it("draws the domain x section grid with gaps and each section's EBITDA share", async () => {
    const api = fakeApi()
    const storeInventory = ref('node', 'sc4', 'Store Inventory')
    render(
      <VctCoverageView
        api={api}
        facts={[
          {
            id: 'f1',
            entity: 'UPS',
            key: 'rate',
            value: '5.9%',
            tags: { node: TRANSPORT, goal: FREIGHT },
            tagged: true,
          },
          {
            id: 'f2',
            entity: 'Dallas warehouse',
            key: 'cycle_count',
            value: '97%',
            tags: { node: storeInventory, goal: null },
            tagged: true,
          },
          {
            id: 'f3',
            entity: 'Team lunch',
            key: 'day',
            value: 'Friday',
            tags: null,
            tagged: false,
          },
        ]}
      />,
    )

    const grid = await screen.findByRole('table')
    const finance = within(grid).getByRole('row', { name: /Finance/ })
    expect(within(finance).getAllByRole('cell')[1]).toHaveAttribute('data-gap', '')
    expect(screen.getByText(/1 listed here waiting for the tagger/)).toBeInTheDocument()

    expect(within(grid).getAllByText(/of EBITDA/).length).toBeGreaterThan(0)
    // The facts themselves are listed by the Tagged facts view, not here.
    expect(screen.queryByText('Dallas warehouse')).not.toBeInTheDocument()
  })
})

describe('TaggerPanel', () => {
  it('shows the last run and corrections, and starts a run', async () => {
    const api = fakeApi()
    render(<TaggerPanel api={api} />)

    expect(await screen.findByText(/25% of 4/)).toBeInTheDocument()
    expect(
      screen.getByText(/6 seen · 6 new · 6 tagged · 2 not business · 0 failed/),
    ).toBeInTheDocument()
    expect(screen.getByText('mo1 → fi4 · 1')).toBeInTheDocument()

    // From here on the backend reports the run in progress.
    vi.mocked(api.tagger).mockResolvedValue({ ...STATUS, running: true })
    fireEvent.click(screen.getByRole('button', { name: 'Run now' }))
    expect(await screen.findByRole('button', { name: 'Running…' })).toBeDisabled()
    expect(api.runTagger).toHaveBeenCalledTimes(1)
    expect(api.runTagger).toHaveBeenCalledWith(false)
  })

  it('re-tags everything on request', async () => {
    const api = fakeApi()
    render(<TaggerPanel api={api} />)

    fireEvent.click(await screen.findByRole('button', { name: 'Re-tag all' }))

    await waitFor(() => expect(api.runTagger).toHaveBeenCalledWith(true))
  })

  it('shows errors', async () => {
    const api = fakeApi({
      tagger: vi
        .fn<VctApi['tagger']>()
        .mockRejectedValue(new ApiError(403, 'Admins only')),
    })
    render(<TaggerPanel api={api} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Admins only')
  })
})

describe('OnboardUser', () => {
  it('suggests nodes from a description and saves the ticked ones for the user', async () => {
    const api = fakeApi()
    render(<OnboardUser api={api} />)

    fireEvent.change(screen.getByLabelText('Email'), {
      target: { value: 'Mahamudul.Hasan@x.com' },
    })
    fireEvent.change(screen.getByLabelText('How their day looks'), {
      target: { value: 'I pick carriers' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Suggest nodes' }))

    const sc6 = await screen.findByRole('checkbox', { name: /sc6 Select Transport/ })
    expect(sc6).toBeChecked()
    fireEvent.click(screen.getByRole('checkbox', { name: /sc4 Store Inventory/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Save 2 nodes' }))

    expect(
      await screen.findByText(/Saved for mahamudul.hasan@x.com: Supply Chain/),
    ).toBeInTheDocument()
    expect(api.setUserNodes).toHaveBeenCalledWith('mahamudul.hasan@x.com', ['sc6', 'sc4'])
  })
})
