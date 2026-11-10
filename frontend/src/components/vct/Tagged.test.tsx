import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { FactTagDetail, TagRef, VctApi, VctMap, VctNode } from '@/api/vct'
import { TaggedFactsView, type TaggedFact } from '@/components/vct/Tagged'
import { resetVctMapCache } from '@/components/vct/vctState'

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
  extra: Partial<TaggedFact> = {},
): TaggedFact {
  return {
    id,
    entity: `Entity ${id}`,
    key: 'key',
    value: `value ${id}`,
    space: 'org/spreetail/user/priya',
    tags: tag ? { node: tag, goal: FREIGHT } : null,
    tagged: true,
    business: true,
    at: '2026-11-09T10:00:00Z',
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

function fakeApi(): VctApi {
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
    reviewFacts: vi.fn<VctApi['reviewFacts']>(),
    coverage: vi.fn<VctApi['coverage']>(),
    tagger: vi.fn<VctApi['tagger']>(),
    runTagger: vi.fn<VctApi['runTagger']>(),
    previewOnboarding: vi.fn<VctApi['previewOnboarding']>(),
    myOnboarding: vi.fn<VctApi['myOnboarding']>(),
    userOnboarding: vi.fn<VctApi['userOnboarding']>(),
    setUserNodes: vi.fn<VctApi['setUserNodes']>(),
  }
}

afterEach(() => resetVctMapCache())

describe('TaggedFactsView', () => {
  it('lists every tagged fact by domain, newest first, with no review buttons', async () => {
    const api = fakeApi()
    render(
      <TaggedFactsView
        api={api}
        facts={[
          fact('old', SC6, { at: '2026-11-01T10:00:00Z' }),
          fact('new', SC9, { at: '2026-11-09T10:00:00Z' }),
          fact('d', FI4),
          fact('waiting', null, { tagged: false }),
        ]}
      />,
    )

    const supply = await screen.findByRole('region', { name: 'Supply Chain' })
    expect(within(supply).getByText(/2 facts · 67% of tagged facts/)).toBeInTheDocument()
    const rows = within(supply).getAllByText(/^Entity /)
    expect(rows.map((r) => r.textContent)).toEqual(['Entity new', 'Entity old'])
    expect(screen.getByRole('button', { name: 'Tagged · 3' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(screen.queryByText('Entity waiting')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Confirm/ })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Node' }))
    expect(
      await screen.findByRole('region', { name: 'sc6 Select Transport' }),
    ).toBeInTheDocument()
  })

  it('opens the editor from the pencil and moves the fact to its new group', async () => {
    const api = fakeApi()
    render(<TaggedFactsView api={api} facts={[fact('a', SC6)]} />)

    await screen.findByRole('region', { name: 'Supply Chain' })
    fireEvent.click(screen.getByRole('button', { name: 'Edit tags for Entity a · key' }))
    const pick = await screen.findByLabelText('Choose another node')
    await waitFor(() => expect(pick).not.toBeDisabled())
    fireEvent.change(pick, { target: { value: 'fi4' } })

    await waitFor(() =>
      expect(api.editTag).toHaveBeenCalledWith('a', {
        kind: 'node',
        action: 'change',
        tag: 'fi4',
      }),
    )
    expect(await screen.findByRole('region', { name: 'Finance' })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Supply Chain' })).not.toBeInTheDocument()
  })

  it('shows facts without a goal and not-business facts in their own tabs', async () => {
    const api = fakeApi()
    render(
      <TaggedFactsView
        api={api}
        facts={[
          fact('a', SC6),
          fact('nogoal', SC9, { tags: { node: SC9, goal: null } }),
          fact('lunch', null, { business: false }),
        ]}
      />,
    )

    fireEvent.click(await screen.findByRole('button', { name: 'Without a goal · 1' }))
    expect(screen.getByText('Entity nogoal')).toBeInTheDocument()
    expect(screen.queryByText('Entity a')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Not business · 1' }))
    const off = screen.getByRole('region', { name: 'Not business' })
    expect(within(off).getByText('Entity lunch')).toBeInTheDocument()
    expect(within(off).getByText('not business')).toBeInTheDocument()
    expect(
      within(off).getByRole('button', { name: 'Edit tags for Entity lunch · key' }),
    ).toBeInTheDocument()
  })
})
