import { act, fireEvent, render, screen, within } from '@testing-library/react'
import type { AskApi, AskCompareResponse, AskResponse } from '@/api/ask'
import type { Me } from '@/api/auth'
import { ApiError } from '@/api/client'
import { mockAskApi } from '@/api/mock/ask'
import { meOf } from '@/api/mock/auth'
import { setMockLatencyScale, userByEmail } from '@/api/mock/backend'
import { clearChats } from '@/components/ask/chatStore'
import { ownScope } from '@/components/ask/layers'
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
  const api = compareApi(vi.fn<AskApi['compare']>(mockAskApi.compare))
  render(<AskPage me={PRIYA} api={api} />)

  await screen.findByRole('button', { name: 'Search in: My space' })
  fireEvent.change(screen.getByLabelText('Question'), {
    target: { value: 'Is dock 3 open?' },
  })
  fireEvent.submit(screen.getByLabelText('Question').closest('form')!)

  await vi.waitFor(() => expect(api.compare).toHaveBeenCalled())
  expect(vi.mocked(api.compare).mock.calls[0]?.[0]).toMatchObject({
    scopes: [ownScope(PRIYA.grants)],
  })
})

async function findAnswer(question: string) {
  return screen.findByRole('region', { name: question }, { timeout: 2000 })
}

const layerHeadings = (answer: HTMLElement) =>
  within(answer)
    .getAllByRole('heading', { level: 4 })
    .map((h) => h.textContent)

function answerWith(layers: AskResponse['layers']): AskResponse {
  return {
    q: 'Is dock 3 open?',
    scopes: ['org/user/u-0001'],
    answered_at: '2026-11-02T10:00:00+00:00',
    layers,
    metadata: {
      total_facts: layers.reduce((n, l) => n + l.facts.length, 0),
      resolution_tier: 'hybrid',
      latency_ms: 9800,
      include_inferred: false,
      trace_ids: ['t-a', 't-b'],
    },
    trace_id: 't-root',
    mode: 'default',
    mode_source: 'config',
    conflicts: [],
  }
}

/** One answer as both modes, the way /ask/compare returns them. */
function bothModes(answer: AskResponse): AskCompareResponse {
  return {
    q: answer.q,
    best_match: { ...answer, mode: 'best_match', mode_source: 'compare' },
    by_layer: { ...answer, mode: 'by_layer', mode_source: 'compare' },
  }
}

/** An API whose compare is stubbed; ask must never be called by Search. */
function compareApi(compare: AskApi['compare']): AskApi {
  return { ask: vi.fn<AskApi['ask']>(mockAskApi.ask), compare }
}

describe('AskPage', () => {
  it('answers the returns question as Priya with Best match and By layer side by side', async () => {
    await renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'What is the returns window?' }))
    const answer = await findAnswer('What is the returns window?')

    expect(within(answer).getByText(/as Priya$/)).toBeInTheDocument()
    const best = within(answer).getByRole('region', { name: 'Best match' })
    const byLayer = within(answer).getByRole('region', { name: 'By layer' })
    // Best match: one list, each fact labelled with its layer.
    expect(best.querySelector('.ask-tally')).toHaveTextContent('Org2Team0Personal1')
    expect(best.querySelectorAll('.ask-flat > .ask-fact')).toHaveLength(2)
    // By layer: one closed card per layer.
    expect(layerHeadings(byLayer)).toEqual([
      'Org org',
      'Team org/team/ops',
      'Personal org/user/u-0001 · Priya',
    ])
  })

  it('keeps match score and trust apart, and opens the source panel with both', async () => {
    await renderPage()

    fireEvent.click(screen.getByRole('button', { name: 'What is the returns window?' }))
    const answer = await findAnswer('What is the returns window?')

    const best = within(answer).getByRole('region', { name: 'Best match' })
    const scores = within(best).getAllByRole('button', {
      name: /^match score \d\.\d\d$/,
    })
    // Trust is its own chip, never the match score's label.
    const [used] = [...best.querySelectorAll('.ask-flat > .ask-fact')]
    expect(used?.querySelector('.ask-trust')).toHaveTextContent('trust 0.95')
    expect(used?.querySelector('.ask-trust')).toHaveAttribute(
      'title',
      expect.stringMatching(/^Structured fact · confidence 0.95 · added 9 Nov 2026$/),
    )

    const first = scores[0]!
    fireEvent.click(first)
    const panel = screen.getByRole('region', { name: 'Source' })
    expect(panel).toHaveFocus()
    expect(within(panel).getByText('Hit id')).toBeInTheDocument()
    expect(within(panel).getByText(/^attribute_[0-9a-f]{6}$/)).toBeInTheDocument()
    expect(within(panel).getByText('Hit text')).toBeInTheDocument()
    expect(within(panel).getByText('Trust').nextElementSibling).toHaveTextContent('0.95')
    expect(within(panel).getByText('Written as').nextElementSibling).toHaveTextContent(
      'Structured fact',
    )
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

  it('shows a failed layer error while the other layers still answer', async () => {
    const api = compareApi(async () =>
      bothModes(
        answerWith([
          {
            layer: 'org',
            area: 'org',
            owner: null,
            facts: [],
            error: 'Agent Memory call failed: timeout',
          },
          {
            layer: 'personal',
            area: 'org/user/u-0001',
            owner: 'Priya',
            facts: [
              {
                fact: 'reno warehouse · dock_3_status = closed',
                source: {
                  kind: 'memory',
                  hit_kind: 'attribute',
                  hit_id: 'attribute_000007',
                  title: null,
                  date: null,
                  text: 'reno warehouse · dock_3_status = closed',
                  score: 0.823,
                },
              },
            ],
            error: null,
          },
        ]),
      ),
    )
    await renderPage(api)

    fireEvent.click(screen.getByRole('button', { name: 'Is dock 3 open?' }))
    const answer = await findAnswer('Is dock 3 open?')

    expect(
      within(answer).getByText(
        'Recall failed for Org org: Agent Memory call failed: timeout',
      ),
    ).toBeInTheDocument()
    // Both columns list it: Best match in its list, By layer in the Personal card.
    expect(
      within(answer).getAllByText('reno warehouse · dock_3_status = closed'),
    ).toHaveLength(2)
    expect(
      within(answer).getAllByRole('button', { name: 'match score 0.82', hidden: true }),
    ).toHaveLength(2)
    expect(within(answer).getByText(/trace t-root/)).toBeInTheDocument()
  })

  it('shows the API error message when every layer fails', async () => {
    const api = compareApi(async () => {
      throw new ApiError(503, 'Agent Memory call failed: x')
    })
    await renderPage(api)

    fireEvent.change(screen.getByLabelText('Question'), { target: { value: 'anything' } })
    fireEvent.submit(screen.getByLabelText('Question').closest('form')!)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Agent Memory call failed: x')
    expect(alert).toHaveTextContent('Every layer failed to answer')
  })

  it('cancel aborts the in-flight ask', async () => {
    let seen: AbortSignal | undefined
    const api = compareApi((_request, signal) => {
      seen = signal
      return new Promise(() => {})
    })
    await renderPage(api)

    fireEvent.click(screen.getByRole('button', { name: 'Is dock 3 open?' }))
    expect(screen.getByText(/Recall can take about 10 s/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(seen?.aborted).toBe(true)
    expect(screen.getByText(/Cancelled/)).toBeInTheDocument()
  })

  it('searches only the ticked spaces, and tells the backend which', async () => {
    const api = compareApi(
      vi.fn<AskApi['compare']>(async () => bothModes(answerWith([]))),
    )
    await renderPage(api)

    fireEvent.click(screen.getByRole('button', { name: /^Search in:/ }))
    fireEvent.click(screen.getByRole('checkbox', { name: /Team ops/ }))

    expect(screen.getByText(/^Reads org → org\/user\/u-0001$/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Search in:/ })).toHaveAccessibleName(
      'Search in: Org + My space',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Is dock 3 open?' }))
    expect(api.compare).toHaveBeenCalledWith(
      { q: 'Is dock 3 open?', scopes: ['org', 'org/user/u-0001'] },
      expect.any(AbortSignal),
    )
  })

  it('searches everything, without narrowing, while every space is ticked', async () => {
    const api = compareApi(
      vi.fn<AskApi['compare']>(async () => bothModes(answerWith([]))),
    )
    await renderPage(api)

    fireEvent.click(screen.getByRole('button', { name: 'Is dock 3 open?' }))

    expect(api.compare).toHaveBeenCalledWith(
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
    const api = compareApi(
      vi.fn<AskApi['compare']>(async () => bothModes(answerWith([]))),
    )
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
    expect(api.compare).not.toHaveBeenCalled()
  })
})

describe('Compare view', () => {
  const askReturns = async () => {
    fireEvent.click(screen.getByRole('button', { name: 'What is the returns window?' }))
    return findAnswer('What is the returns window?')
  }

  it('sends one click as one compare request, with no mode picker', async () => {
    const api = compareApi(vi.fn<AskApi['compare']>(mockAskApi.compare))
    await renderPage(api)
    expect(screen.queryByRole('radiogroup')).not.toBeInTheDocument()
    expect(screen.getByText(/together, side by side/)).toBeInTheDocument()

    await askReturns()
    // One request, so every scope is recalled once for both columns.
    expect(api.compare).toHaveBeenCalledTimes(1)
    expect(api.ask).not.toHaveBeenCalled()
  })

  it('lines up the 30 vs 60 disagreement: the value Best match used next to every By layer value', async () => {
    await renderPage()
    const answer = await askReturns()

    const table = within(answer).getByRole('table')
    expect(table).toHaveTextContent('1 point where the layers disagree')
    const row = within(table).getAllByRole('row')[1]!
    expect(within(row).getByRole('rowheader')).toHaveTextContent(
      'returns policywindow_days',
    )
    const [picked, all] = within(row).getAllByRole('cell')
    expect(picked).toHaveTextContent('30')
    expect(picked).toHaveTextContent('Org')
    expect(picked).toHaveTextContent('Used')
    expect(picked).toHaveTextContent('Scores within 0.10, so the broader Org layer wins')
    expect(picked).not.toHaveTextContent('60')
    expect(all).toHaveTextContent('30')
    expect(all).toHaveTextContent('60')
    expect(all).toHaveTextContent('Personal')
    expect(all).not.toHaveTextContent('Used')
    // Each value shows the trust of its source: Org structured, Personal from chat.
    expect(picked!.querySelector('.ask-trust')).toHaveTextContent('trust 0.95')
    expect([...all!.querySelectorAll('.ask-trust')].map((t) => t.textContent)).toEqual([
      'trust 0.95',
      'trust 0.50',
    ])
  })

  it('Best match puts the Org value first and folds the other under it', async () => {
    await renderPage()
    const answer = await askReturns()
    const best = within(answer).getByRole('region', { name: 'Best match' })

    const [first] = [...best.querySelectorAll('.ask-flat > .ask-fact')]
    expect(first).toHaveTextContent('returns policy · window_days = 30')
    expect(first).toHaveTextContent('Used')
    expect(first?.querySelector('.ask-layer-tag')).toHaveTextContent('Org')
    const folded = within(first as HTMLElement)
      .getByText('1 set aside')
      .closest('details')!
    expect(folded).toHaveTextContent('returns policy · window_days = 60')
    expect(folded).toHaveTextContent('Disagrees with the chosen Org value: 30')
  })

  it('By layer cards start closed, count what disagrees, and expand all at once', async () => {
    await renderPage()
    const answer = await askReturns()
    const byLayer = within(answer).getByRole('region', { name: 'By layer' })

    const cards = [
      ...byLayer.querySelectorAll('details.ask-layer'),
    ] as HTMLDetailsElement[]
    expect(cards.every((card) => !card.open)).toBe(true)
    expect(cards[0]).toHaveTextContent('1 disagree')
    expect(cards[1]).not.toHaveTextContent('disagree')
    expect(within(byLayer).queryByText('Used')).not.toBeInTheDocument()

    fireEvent.click(within(byLayer).getByRole('button', { name: 'Expand all' }))
    const reopened = [
      ...byLayer.querySelectorAll('details.ask-layer'),
    ] as HTMLDetailsElement[]
    expect(reopened.every((card) => card.open)).toBe(true)
  })

  it('says so when the layers agree, with no table', async () => {
    await renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Is dock 3 open?' }))
    const answer = await findAnswer('Is dock 3 open?')
    expect(within(answer).queryByRole('table')).not.toBeInTheDocument()
    expect(
      within(answer).getByText(/No disagreements between layers/),
    ).toBeInTheDocument()
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
