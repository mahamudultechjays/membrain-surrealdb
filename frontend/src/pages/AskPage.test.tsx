import { act, fireEvent, render, screen, within } from '@testing-library/react'
import type { AskApi, AskResponse } from '@/api/ask'
import type { Me } from '@/api/auth'
import { ApiError } from '@/api/client'
import { mockAskApi } from '@/api/mock/ask'
import { meOf } from '@/api/mock/auth'
import { setMockLatencyScale, userByEmail } from '@/api/mock/backend'
import { clearChats } from '@/components/ask/chatStore'
import { ownScope } from '@/components/ask/layers'
import type { VctApi } from '@/api/vct'
import AskPage from '@/pages/AskPage'

beforeAll(() => setMockLatencyScale(0))
afterAll(() => setMockLatencyScale(1))

/** Priya, as the mock signs her in: org, her team (ops) and her own space. */
const PRIYA = meOf(userByEmail('priya@example.com')!)

/**
 * Renders the page, which opens on Priya's own space, then ticks every space:
 * most tests here are about answers drawn from all three layers.
 */
async function renderPage(api: AskApi = mockAskApi) {
  render(<AskPage me={PRIYA} api={api} />)
  const picker = await screen.findByRole('button', { name: 'Search in: My space' })
  fireEvent.click(picker)
  fireEvent.click(screen.getByRole('button', { name: 'Select all' }))
  fireEvent.click(picker)
  await screen.findByRole('button', { name: 'Search in: All spaces' })
}

it('opens on the user’s own space, and searches only that until they widen it', async () => {
  const api: AskApi = { ask: vi.fn<AskApi['ask']>(mockAskApi.ask) }
  render(<AskPage me={PRIYA} api={api} />)

  await screen.findByRole('button', { name: 'Search in: My space' })
  fireEvent.change(screen.getByLabelText('Question'), {
    target: { value: 'Is dock 3 open?' },
  })
  fireEvent.submit(screen.getByLabelText('Question').closest('form')!)

  await vi.waitFor(() => expect(api.ask).toHaveBeenCalled())
  expect(vi.mocked(api.ask).mock.calls[0]?.[0]).toMatchObject({
    scopes: [ownScope(PRIYA.grants)],
  })
})

async function findAnswer(question: string) {
  return screen.findByRole('region', { name: question }, { timeout: 2000 })
}

const resultTexts = (answer: HTMLElement) =>
  within(within(answer).getByRole('list', { name: 'Default results' }))
    .getAllByRole('listitem')
    .map((item) => item.querySelector('.ask-fact-text')?.textContent)

function answerWith(facts: AskResponse['facts']): AskResponse {
  return {
    q: 'Is dock 3 open?',
    scopes: ['org', 'org/user/u-0001'],
    answered_at: '2026-11-02T10:00:00+00:00',
    facts,
    metadata: {
      total_facts: facts.length,
      resolution_tier: 'hybrid',
      latency_ms: 9800,
      include_inferred: false,
      trace_ids: ['t-a'],
    },
    trace_id: 't-root',
  }
}

describe('AskPage', () => {
  it('answers as one ranked list across every scope, with no layer grouping or verdict', async () => {
    await renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'What is the returns window?' }))
    const answer = await findAnswer('What is the returns window?')

    const texts = resultTexts(answer)
    // Both values come back side by side, as Agent Memory ranks them.
    expect(texts.some((t) => t?.includes('window_days = 30'))).toBe(true)
    expect(texts.some((t) => t?.includes('window_days = 60'))).toBe(true)
    // Two columns, Default and Value-driven; no layer headings inside them.
    expect(
      within(answer)
        .getAllByRole('heading', { level: 3 })
        .map((h) => h.textContent),
    ).toEqual(['Default', 'Value-driven'])
    expect(within(answer).queryByRole('note')).not.toBeInTheDocument()
    expect(within(answer).getByText(/3 scopes read/)).toBeInTheDocument()
    expect(within(answer).getByText(/as Priya$/)).toBeInTheDocument()
  })

  it('labels the score as a match score and opens the source panel with the hit id', async () => {
    await renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'What is the returns window?' }))
    const answer = await findAnswer('What is the returns window?')

    const scores = within(answer).getAllByRole('button', {
      name: /^match score \d\.\d\d$/,
    })
    expect(within(answer).queryByText(/trust/i)).not.toBeInTheDocument()

    const first = scores[0]!
    fireEvent.click(first)
    const panel = screen.getByRole('region', { name: 'Source' })
    expect(panel).toHaveFocus()
    expect(within(panel).getByText('Hit id')).toBeInTheDocument()
    expect(within(panel).getByText(/^attribute_[0-9a-f]{6}$/)).toBeInTheDocument()
    expect(within(panel).getByText('Hit text')).toBeInTheDocument()
    // Null title and date stay hidden.
    expect(within(panel).queryByText('Title')).not.toBeInTheDocument()
    expect(
      within(panel).getByText(
        'Agent Memory recall returns no document title or position yet.',
      ),
    ).toBeInTheDocument()

    fireEvent.keyDown(panel, { key: 'Escape' })
    expect(screen.queryByRole('region', { name: 'Source' })).not.toBeInTheDocument()
    expect(first).toHaveFocus()
  })

  it('keeps the order the backend returned, with each match score and the traces', async () => {
    const fact = (id: string, text: string, score: number) => ({
      fact: text,
      source: {
        kind: 'memory' as const,
        hit_kind: 'attribute',
        hit_id: id,
        title: null,
        date: null,
        text,
        score,
      },
    })
    const api: AskApi = {
      ask: async () =>
        answerWith([
          fact('attribute_000007', 'reno warehouse · dock_3_status = closed', 0.823),
          fact('attribute_000008', 'reno warehouse · dock_3_status = open', 0.91),
        ]),
    }
    await renderPage(api)

    fireEvent.click(screen.getByRole('button', { name: 'Is dock 3 open?' }))
    const answer = await findAnswer('Is dock 3 open?')

    expect(resultTexts(answer)).toEqual([
      'reno warehouse · dock_3_status = closed',
      'reno warehouse · dock_3_status = open',
    ])
    expect(
      within(answer).getByText('reno warehouse · dock_3_status = closed'),
    ).toBeInTheDocument()
    expect(
      within(answer).getByRole('button', { name: 'match score 0.82' }),
    ).toBeInTheDocument()
    expect(within(answer).getByText(/trace t-root/)).toBeInTheDocument()
    expect(within(answer).getByText('memory trace t-a')).toBeInTheDocument()
  })

  it('says nothing was found when the recall has no hits', async () => {
    await renderPage({ ask: async () => answerWith([]) })

    fireEvent.click(screen.getByRole('button', { name: 'Is dock 3 open?' }))
    const answer = await findAnswer('Is dock 3 open?')

    expect(
      within(answer).getByText('Nothing found in org, org/user/u-0001'),
    ).toBeInTheDocument()
  })

  it('shows the API error message when the recall fails', async () => {
    const api: AskApi = {
      ask: async () => {
        throw new ApiError(503, 'Agent Memory call failed: x')
      },
    }
    await renderPage(api)

    fireEvent.change(screen.getByLabelText('Question'), { target: { value: 'anything' } })
    fireEvent.submit(screen.getByLabelText('Question').closest('form')!)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Agent Memory call failed: x')
    expect(alert).toHaveTextContent('Agent Memory did not answer')
  })

  it('cancel aborts the in-flight ask', async () => {
    let seen: AbortSignal | undefined
    const api: AskApi = {
      ask: (_request, signal) => {
        seen = signal
        return new Promise(() => {})
      },
    }
    await renderPage(api)

    fireEvent.click(screen.getByRole('button', { name: 'Is dock 3 open?' }))
    expect(screen.getByText(/Recall can take about 10 s/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(seen?.aborted).toBe(true)
    expect(screen.getByText(/Cancelled/)).toBeInTheDocument()
  })

  it('searches only the ticked spaces, and tells the backend which', async () => {
    const api: AskApi = { ask: vi.fn<AskApi['ask']>(async () => answerWith([])) }
    await renderPage(api)

    fireEvent.click(screen.getByRole('button', { name: /^Search in:/ }))
    fireEvent.click(screen.getByRole('checkbox', { name: /Team ops/ }))

    expect(screen.getByText(/^Reads org, org\/user\/u-0001$/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Search in:/ })).toHaveAccessibleName(
      'Search in: Org + My space',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Is dock 3 open?' }))
    expect(api.ask).toHaveBeenCalledWith(
      { q: 'Is dock 3 open?', scopes: ['org', 'org/user/u-0001'] },
      expect.any(AbortSignal),
    )
  })

  it('searches everything, without narrowing, while every space is ticked', async () => {
    const api: AskApi = { ask: vi.fn<AskApi['ask']>(async () => answerWith([])) }
    await renderPage(api)

    fireEvent.click(screen.getByRole('button', { name: 'Is dock 3 open?' }))

    expect(api.ask).toHaveBeenCalledWith(
      { q: 'Is dock 3 open?', scopes: [] },
      expect.any(AbortSignal),
    )
  })

  it("names someone else's space by its owner", async () => {
    const me: Me = {
      ...PRIYA,
      grants: [
        ...PRIYA.grants,
        { scope_path: 'org/user/u-0003', access: 'read', layer: 'team', owner: 'Deena' },
      ],
    }
    render(<AskPage me={me} api={mockAskApi} />)

    fireEvent.click(screen.getByRole('button', { name: 'Search in: My space' }))

    expect(screen.getByRole('checkbox', { name: /Deena/ })).not.toBeChecked()
    expect(screen.getByRole('checkbox', { name: /My space/ })).toBeChecked()
  })

  it('can deselect every space, which leaves nothing to ask, then select all again', async () => {
    const api: AskApi = { ask: vi.fn<AskApi['ask']>(async () => answerWith([])) }
    await renderPage(api)

    fireEvent.click(screen.getByRole('button', { name: /^Search in:/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Deselect all' }))

    expect(screen.getByRole('checkbox', { name: /My space/ })).not.toBeChecked()
    expect(screen.getByRole('button', { name: 'Search in: none' })).toBeInTheDocument()
    expect(screen.getByText(/^Reads nothing/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Is dock 3 open?' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Deselect all' })).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: 'Select all' }))
    expect(
      screen.getByRole('button', { name: 'Search in: All spaces' }),
    ).toBeInTheDocument()
    expect(api.ask).not.toHaveBeenCalled()
  })
})

describe('AskPage modes', () => {
  afterEach(() => {
    window.location.hash = ''
    clearChats()
  })

  it('opens in search mode, with the mode switch pointing at the two sub-URLs', async () => {
    await renderPage()

    const modes = screen.getByRole('navigation', { name: 'Ask mode' })
    const search = within(modes).getByRole('link', { name: 'Search' })
    expect(search).toHaveAttribute('aria-current', 'page')
    expect(search).toHaveAttribute('href', '#/ask/search')
    expect(within(modes).getByRole('link', { name: 'Chat' })).toHaveAttribute(
      'href',
      '#/ask/chat',
    )
    expect(screen.getByLabelText('Question')).toBeInTheDocument()
  })

  it('#/ask/reflect shows reflection, the third mode', () => {
    window.location.hash = '#/ask/reflect'

    render(<AskPage me={PRIYA} api={mockAskApi} />)

    const reflect = screen.getByRole('link', { name: 'Reflect' })
    expect(reflect).toHaveAttribute('href', '#/ask/reflect')
    expect(reflect).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('button', { name: 'Reflect' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Message')).not.toBeInTheDocument()
  })

  it('#/ask/chat shows the chat instead of search', () => {
    window.location.hash = '#/ask/chat'

    render(<AskPage me={PRIYA} api={mockAskApi} />)

    expect(screen.getByLabelText('Message')).toBeInTheDocument()
    expect(screen.queryByLabelText('Question')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Chat' })).toHaveAttribute(
      'aria-current',
      'page',
    )
  })

  it('keeps what was typed in each mode when switching between them', async () => {
    await renderPage()
    fireEvent.change(screen.getByLabelText('Question'), {
      target: { value: 'Is dock 3 open?' },
    })

    act(() => {
      window.location.hash = '#/ask/chat'
      window.dispatchEvent(new HashChangeEvent('hashchange'))
    })
    fireEvent.change(screen.getByLabelText('Message'), {
      target: { value: 'Who runs dock 3?' },
    })
    expect(screen.getByLabelText('Question')).not.toBeVisible()

    act(() => {
      window.location.hash = '#/ask/search'
      window.dispatchEvent(new HashChangeEvent('hashchange'))
    })
    expect(screen.getByLabelText('Question')).toHaveValue('Is dock 3 open?')
    // Only the mode on screen puts its picker in the header.
    expect(screen.getAllByRole('button', { name: /^Search in/ })).toHaveLength(1)

    act(() => {
      window.location.hash = '#/ask/chat'
      window.dispatchEvent(new HashChangeEvent('hashchange'))
    })
    expect(screen.getByLabelText('Message')).toHaveValue('Who runs dock 3?')
  })
})

describe('AskPage value-driven filter', () => {
  const vctApi = {
    map: vi.fn<VctApi['map']>().mockResolvedValue({
      scope: 'org/spreetail/vct/nodes',
      domains: [
        {
          id: 'supply-chain',
          name: 'Supply Chain',
          nodes: [],
        },
        { id: 'finance', name: 'Finance', nodes: [] },
      ],
      sections: [],
    } as unknown as Awaited<ReturnType<VctApi['map']>>),
    myOnboarding: vi.fn<VctApi['myOnboarding']>().mockResolvedValue({
      email: 'priya@example.com',
      onboarded: true,
      primary_work: 'I pick carriers',
      nodes: [],
      domains: [{ id: 'supply-chain', name: 'Supply Chain' }],
    }),
  } as unknown as VctApi

  it('starts on the user’s domains and re-asks when the filter changes', async () => {
    const api: AskApi = { ask: vi.fn<AskApi['ask']>(mockAskApi.ask) }
    render(<AskPage me={PRIYA} api={api} vctApi={vctApi} />)

    expect(
      await screen.findByRole('button', { name: 'Remove domain Supply Chain' }),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Is dock 3 open?' }))
    await vi.waitFor(() => expect(api.ask).toHaveBeenCalledTimes(1))
    expect(vi.mocked(api.ask).mock.calls[0]?.[0]).toMatchObject({
      domains: ['supply-chain'],
    })

    await findAnswer('Is dock 3 open?')
    fireEvent.change(screen.getByLabelText('Domain'), { target: { value: 'finance' } })
    await vi.waitFor(() => expect(api.ask).toHaveBeenCalledTimes(2))
    expect(vi.mocked(api.ask).mock.calls[1]?.[0]).toMatchObject({
      q: 'Is dock 3 open?',
      domains: ['supply-chain', 'finance'],
    })
  })
})
