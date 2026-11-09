import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { FactTagDetail, TagRef, VctApi, VctMap, VctNode } from '@/api/vct'
import { ReviewBanner, ReviewView, type ReviewFact } from '@/components/vct/Review'
import { inReview, resetVctMapCache, timeLeft } from '@/components/vct/vctState'

const NOW = Date.parse('2026-11-09T12:00:00Z')
const HOURS_AGO = (h: number) => new Date(NOW - h * 3600_000).toISOString()

const node = (id: string, name: string, domain: string, section: string): VctNode => ({
  id,
  name,
  description: '',
  domain_id: domain,
  section_id: section,
})

const MAP: VctMap = {
  topology_version: 'test',
  domains: [
    {
      id: 'supply-chain',
      name: 'Supply Chain',
      nodes: [
        node('sc6', 'Select Transport', 'supply-chain', 'fulfillment'),
        node('sc9', 'Process Returns', 'supply-chain', 'post-sale'),
      ],
    },
    {
      id: 'finance',
      name: 'Finance',
      nodes: [node('fi4', 'Manage Cash & Payouts', 'finance', 'post-sale')],
    },
  ],
  sections: [
    {
      id: 'fulfillment',
      label: 'Fulfil',
      ebitda_weight: 0.3,
      goals: [{ id: 'ff-mgmt5', name: 'Freight Cost', description: '', weight: 0.05 }],
    },
    { id: 'post-sale', label: 'Post-sale', ebitda_weight: 0.1, goals: [] },
  ],
}

function ref(kind: 'node' | 'goal', id: string, name: string, domain?: string): TagRef {
  return {
    kind,
    id,
    name,
    section_id: '',
    section: null,
    domain_id: domain ?? null,
    source: 'auto',
    rank: 1,
  }
}

const SC6 = ref('node', 'sc6', 'Select Transport', 'supply-chain')
const SC9 = ref('node', 'sc9', 'Process Returns', 'supply-chain')
const FI4 = ref('node', 'fi4', 'Manage Cash & Payouts', 'finance')
const FREIGHT = ref('goal', 'ff-mgmt5', 'Freight Cost')

function fact(
  id: string,
  tag: TagRef | null,
  extra: Partial<ReviewFact> = {},
): ReviewFact {
  return {
    id,
    entity: `Entity ${id}`,
    key: 'key',
    value: `value ${id}`,
    space: 'org/spreetail/user/priya',
    tags: tag ? { node: tag, goal: FREIGHT } : null,
    business: true,
    taggedAt: new Date(Date.now() - 3600_000).toISOString(),
    reviewedAt: null,
    ...extra,
  }
}

function detail(id: string, overrides: Partial<FactTagDetail> = {}): FactTagDetail {
  return {
    fact_id: id,
    scope: 'org/spreetail/user/priya',
    business: true,
    tagged_at: null,
    reviewed_at: null,
    reviewed_by: null,
    guess_nodes: [],
    guess_goals: [],
    nodes: [SC6, { ...FI4, rank: 2 }],
    goals: [FREIGHT],
    ...overrides,
  }
}

function fakeApi(overrides: Partial<VctApi> = {}): VctApi {
  return {
    map: vi.fn<VctApi['map']>().mockResolvedValue(MAP),
    factTags: vi
      .fn<VctApi['factTags']>()
      .mockImplementation((id) => Promise.resolve(detail(id))),
    editTag: vi
      .fn<VctApi['editTag']>()
      .mockImplementation((id, edit) =>
        Promise.resolve(
          detail(id, edit.tag === 'fi4' ? { nodes: [{ ...FI4, source: 'user' }] } : {}),
        ),
      ),
    reviewFacts: vi
      .fn<VctApi['reviewFacts']>()
      .mockImplementation((ids) => Promise.resolve({ done: ids, skipped: [] })),
    coverage: vi.fn<VctApi['coverage']>(),
    tagger: vi.fn<VctApi['tagger']>(),
    runTagger: vi.fn<VctApi['runTagger']>(),
    previewOnboarding: vi.fn<VctApi['previewOnboarding']>(),
    userOnboarding: vi.fn<VctApi['userOnboarding']>(),
    setUserNodes: vi.fn<VctApi['setUserNodes']>(),
    ...overrides,
  }
}

afterEach(() => resetVctMapCache())

describe('review window', () => {
  it('keeps facts tagged in the last 2 days that nobody reviewed', () => {
    const facts = [
      { id: 'new', taggedAt: HOURS_AGO(3), reviewedAt: null },
      { id: 'old', taggedAt: HOURS_AGO(50), reviewedAt: null },
      { id: 'done', taggedAt: HOURS_AGO(3), reviewedAt: HOURS_AGO(1) },
      { id: 'never', taggedAt: null, reviewedAt: null },
    ]
    expect(inReview(facts, NOW).map((f) => f.id)).toEqual(['new'])
    expect(timeLeft(HOURS_AGO(3), NOW)).toBe('1 day 21 h')
    expect(timeLeft(HOURS_AGO(24), NOW)).toBe('1 day')
    expect(timeLeft(HOURS_AGO(42), NOW)).toBe('6 h')
    expect(timeLeft(HOURS_AGO(47.5), NOW)).toBe('under 1 h')
  })

  it('shows a banner only when something waits', () => {
    const { rerender } = render(<ReviewBanner count={3} />)
    expect(screen.getByText('3 new tags to review')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Review now' })).toHaveAttribute(
      'href',
      '#/brain/review',
    )
    rerender(<ReviewBanner count={0} />)
    expect(screen.queryByText(/to review/)).not.toBeInTheDocument()
  })
})

describe('ReviewView', () => {
  it('groups by domain with section and node counts, and confirms one or all', async () => {
    const api = fakeApi()
    const facts = [
      fact('a', SC6),
      fact('b', SC6),
      fact('c', SC9),
      fact('d', FI4),
      fact('e', SC6, { reviewedAt: HOURS_AGO(1) }),
    ]
    render(<ReviewView facts={facts} api={api} />)

    const supply = await screen.findByRole('region', { name: 'Supply Chain' })
    await waitFor(() =>
      expect(
        within(supply).getByText(/mostly Fulfil \(2\), Post-sale \(1\)/),
      ).toBeInTheDocument(),
    )
    expect(within(supply).getByText(/Select Transport · 2/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'New tags · 4' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )

    fireEvent.click(within(supply).getAllByRole('button', { name: 'Confirm' })[0]!)
    await waitFor(() =>
      expect(api.editTag).toHaveBeenCalledWith('a', { action: 'confirm' }),
    )
    expect(
      await screen.findByRole('button', { name: 'New tags · 3' }),
    ).toBeInTheDocument()

    const finance = screen.getByRole('region', { name: 'Finance' })
    fireEvent.click(within(finance).getByRole('button', { name: 'Confirm all 1' }))
    await waitFor(() => expect(api.reviewFacts).toHaveBeenCalledWith(['d'], 'confirm'))
    await waitFor(() =>
      expect(screen.queryByRole('region', { name: 'Finance' })).not.toBeInTheDocument(),
    )
  })

  it('changes a node from the picker under the row, and regroups by node', async () => {
    const api = fakeApi()
    render(<ReviewView facts={[fact('a', SC6)]} api={api} />)

    fireEvent.click(
      await screen.findByRole('button', { name: 'Change node: sc6 Select Transport' }),
    )
    fireEvent.click(
      await screen.findByRole('button', { name: /fi4 Manage Cash & Payouts · Finance/ }),
    )

    await waitFor(() =>
      expect(api.editTag).toHaveBeenCalledWith('a', {
        kind: 'node',
        action: 'change',
        tag: 'fi4',
      }),
    )
    expect(await screen.findByRole('region', { name: 'Finance' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Node' }))
    expect(
      screen.getByRole('region', { name: 'fi4 Manage Cash & Payouts' }),
    ).toBeInTheDocument()
  })

  it('shows four facts per group, then more on request, and folds a group', async () => {
    const facts = ['a', 'b', 'c', 'd', 'e', 'f'].map((id) => fact(id, SC6))
    render(<ReviewView facts={facts} api={fakeApi()} />)

    const group = await screen.findByRole('region', { name: 'Supply Chain' })
    expect(within(group).getByText('Showing 4 of 6')).toBeInTheDocument()
    fireEvent.click(within(group).getByRole('button', { name: 'Show 2 more' }))
    expect(within(group).getAllByRole('button', { name: 'Confirm' })).toHaveLength(6)

    fireEvent.click(within(group).getByRole('button', { name: 'Supply Chain' }))
    expect(within(group).queryAllByRole('button', { name: 'Confirm' })).toHaveLength(0)
  })

  it('lists not-business facts with their best guess, to tag or keep', async () => {
    const guessed = detail('x', {
      business: false,
      nodes: [],
      goals: [],
      guess_nodes: [SC9],
      guess_goals: [FREIGHT],
    })
    const api = fakeApi({
      factTags: vi.fn<VctApi['factTags']>().mockResolvedValue(guessed),
    })
    const facts = [
      fact('x', null, { business: false }),
      fact('y', null, { business: false }),
    ]
    render(<ReviewView facts={facts} api={api} />)

    fireEvent.click(screen.getByRole('button', { name: 'Marked not business · 2' }))
    const tagIt = await screen.findAllByRole('button', { name: 'Tag it' })
    await waitFor(() => expect(tagIt[0]).not.toBeDisabled())
    expect(screen.getAllByText(/guess sc9 Process Returns/)).toHaveLength(2)

    fireEvent.click(tagIt[0]!)
    fireEvent.click(screen.getAllByRole('button', { name: 'Keep' })[1]!)
    await waitFor(() =>
      expect(api.editTag).toHaveBeenCalledWith('x', { action: 'tag_guesses' }),
    )
    expect(api.editTag).toHaveBeenCalledWith('y', { action: 'keep' })
    expect(
      await screen.findByText('No new facts were marked not business.'),
    ).toBeInTheDocument()
  })

  it('says when there is nothing to review, and shows errors', async () => {
    const failing = fakeApi({
      editTag: vi
        .fn<VctApi['editTag']>()
        .mockRejectedValue(new Error('Agent Memory down')),
    })
    const { unmount } = render(<ReviewView facts={[]} api={failing} />)
    expect(screen.getByText(/Nothing new to review/)).toBeInTheDocument()
    unmount()

    render(<ReviewView facts={[fact('a', SC6)]} api={failing} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Not business' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Agent Memory down')
  })
})
