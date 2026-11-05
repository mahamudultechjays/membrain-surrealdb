import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import type { ChatApi, ChatRequest, ChatResponse } from '@/api/chat'
import { ApiError } from '@/api/client'
import { meOf } from '@/api/mock/auth'
import { userByEmail } from '@/api/mock/backend'
import AskChat from '@/components/ask/AskChat'
import { ownScope } from '@/components/ask/layers'
import { clearChats } from '@/components/ask/chatStore'

/** Priya, as the mock signs her in: org, her team (ops) and her own space. */
const PRIYA = meOf(userByEmail('priya@example.com')!)

// The conversation outlives the component, so each test starts from a clean one.
afterEach(() => clearChats())

function reply(over: Partial<ChatResponse> = {}): ChatResponse {
  return {
    reply: 'Acme ships to Reno [S1]. Lead time is 18 days [S2].',
    session_id: 'sess-1',
    scopes: ['org', 'org/user/u-0001'],
    citations: [
      {
        marker: 'S1',
        id: 'attribute:a1',
        kind: 'attribute',
        snippet: 'Acme Logistics ships to Reno warehouse',
        score: 0.49,
        document_title: null,
        position_percent: null,
        role: null,
        occurred_at: null,
      },
      {
        marker: 'S2',
        id: 'chunk:c1',
        kind: 'chunk',
        snippet: 'Lead time rose to 18 days',
        score: 0.31,
        document_title: 'Ops manual',
        position_percent: 40,
        role: null,
        occurred_at: null,
      },
    ],
    facts_saved: 0,
    trace_id: 'tr-1',
    ...over,
  }
}

/** Answers from a queue and records every request. */
function fakeApi(...answers: (ChatResponse | Error)[]) {
  const requests: ChatRequest[] = []
  const api: ChatApi = {
    send: (request) => {
      requests.push(request)
      const next = answers.shift() ?? reply()
      return next instanceof Error ? Promise.reject(next) : Promise.resolve(next)
    },
  }
  return { api, requests }
}

function send(text: string) {
  fireEvent.change(screen.getByLabelText('Message'), { target: { value: text } })
  fireEvent.click(screen.getByRole('button', { name: 'Send' }))
}

const lastAnswer = async () => {
  const answers = await screen.findAllByRole('article', { name: /^Answer/ })
  return answers[answers.length - 1]!
}

describe('AskChat', () => {
  it('says up front that questions are saved to your own space', () => {
    render(<AskChat me={PRIYA} api={fakeApi().api} />)

    expect(screen.getByText(/saved to your own space/i)).toBeInTheDocument()
  })

  it('starts a new conversation on Priya’s own space, and shows the reply with linked sources', async () => {
    const { api, requests } = fakeApi()
    render(<AskChat me={PRIYA} api={api} />)

    send('Where does Acme ship?')
    const answer = await lastAnswer()

    expect(requests).toEqual([
      {
        message: 'Where does Acme ship?',
        session_id: null,
        scopes: [ownScope(PRIYA.grants)],
      },
    ])
    expect(screen.getByText('Where does Acme ship?')).toBeInTheDocument()
    const marker = within(answer).getByRole('link', { name: 'Source S1' })
    const source = within(answer).getByText('Acme Logistics ships to Reno warehouse')
    expect(marker.getAttribute('href')).toBe(`#${source.closest('li')!.id}`)
    expect(within(answer).getByText(/Ops manual/)).toBeInTheDocument()
    expect(within(answer).getByText('match 0.49')).toBeInTheDocument()
  })

  it('continues the same conversation on a follow-up', async () => {
    const { api, requests } = fakeApi()
    render(<AskChat me={PRIYA} api={api} />)

    send('Where does Acme ship?')
    await lastAnswer()
    send('And its lead time?')
    await waitFor(() =>
      expect(screen.getAllByRole('article', { name: /^Answer/ })).toHaveLength(2),
    )

    expect(requests[1]).toMatchObject({
      message: 'And its lead time?',
      session_id: 'sess-1',
    })
  })

  it('New chat clears the conversation and forgets the session', async () => {
    const { api, requests } = fakeApi()
    render(<AskChat me={PRIYA} api={api} />)
    send('Where does Acme ship?')
    await lastAnswer()

    fireEvent.click(screen.getByRole('button', { name: 'New chat' }))
    expect(screen.queryByRole('article', { name: /^Answer/ })).not.toBeInTheDocument()
    send('Fresh question')
    await lastAnswer()

    expect(requests[1]).toMatchObject({ session_id: null })
  })

  it('an expired session says so and the next message starts over', async () => {
    const { api, requests } = fakeApi(
      reply(),
      new ApiError(404, 'No such chat session for this user.'),
    )
    render(<AskChat me={PRIYA} api={api} />)
    send('Where does Acme ship?')
    await lastAnswer()

    send('And its lead time?')
    expect(await screen.findByRole('alert')).toHaveTextContent(/start a new chat/i)
    send('Try again')
    await screen.findAllByRole('article', { name: /^Answer/ })

    expect(requests[2]).toMatchObject({ session_id: null })
  })

  it('reports a failure without losing the question', async () => {
    const { api } = fakeApi(new ApiError(503, 'Agent Memory call failed: down'))
    render(<AskChat me={PRIYA} api={api} />)

    send('Where does Acme ship?')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Agent Memory call failed: down',
    )
    expect(screen.getByText('Where does Acme ship?')).toBeInTheDocument()
  })

  it('a reply with no sources says nothing was cited', async () => {
    const { api } = fakeApi(reply({ reply: 'I have nothing on that.', citations: [] }))
    render(<AskChat me={PRIYA} api={api} />)

    send('Unknown thing?')
    const answer = await lastAnswer()

    expect(within(answer).getByText('No sources cited.')).toBeInTheDocument()
  })
})

describe('AskChat keeps the conversation', () => {
  it('is still there after leaving the page and coming back, and follow-ups continue it', async () => {
    const { api, requests } = fakeApi()
    const first = render(<AskChat me={PRIYA} api={api} />)
    send('Where does Acme ship?')
    await lastAnswer()

    first.unmount()
    render(<AskChat me={PRIYA} api={api} />)

    expect(screen.getByText('Where does Acme ship?')).toBeInTheDocument()
    expect(await lastAnswer()).toBeInTheDocument()
    send('And its lead time?')
    expect(requests[1]).toMatchObject({ session_id: 'sess-1' })
  })

  it('a reply that arrives while away is shown on return', async () => {
    let answer!: (r: ChatResponse) => void
    const api: ChatApi = {
      send: () =>
        new Promise((resolve) => {
          answer = resolve
        }),
    }
    const first = render(<AskChat me={PRIYA} api={api} />)
    send('Slow question?')

    first.unmount()
    answer(reply())
    await Promise.resolve()
    render(<AskChat me={PRIYA} api={api} />)

    expect(await lastAnswer()).toHaveTextContent('Acme ships to Reno')
  })

  it('is cleared by clearChats, as on sign-out', async () => {
    const { api } = fakeApi()
    const first = render(<AskChat me={PRIYA} api={api} />)
    send('Where does Acme ship?')
    await lastAnswer()

    first.unmount()
    clearChats()
    render(<AskChat me={PRIYA} api={api} />)

    expect(screen.queryByText('Where does Acme ship?')).not.toBeInTheDocument()
  })
})

describe('AskChat formats replies', () => {
  const MARKDOWN = [
    'Here is a summary of the records you have:',
    '',
    '* **Acme Logistics** (Carrier):',
    '  * **Destination:** Ships to the Reno warehouse [S1].',
    '  * **Lead Time:** 18 days [S2].',
    '* **Dock 3**: a `location`',
  ].join('\n')

  it('renders bold, nested lists and code, with markers still linked', async () => {
    const { api } = fakeApi(reply({ reply: MARKDOWN }))
    render(<AskChat me={PRIYA} api={api} />)

    send('Summary?')
    const answer = await lastAnswer()

    expect(answer.textContent).not.toContain('**')
    expect(within(answer).getByText('Acme Logistics').tagName).toBe('STRONG')
    expect(within(answer).getByText('location').tagName).toBe('CODE')
    const [outer] = within(answer)
      .getAllByRole('list')
      .filter((l) => l.tagName === 'UL')
    expect(within(outer!).getAllByRole('listitem')).toHaveLength(4)
    expect(within(answer).getByRole('link', { name: 'Source S1' })).toBeInTheDocument()
    expect(within(answer).getByRole('link', { name: 'Source S2' })).toBeInTheDocument()
  })

  it('shows HTML in a reply as text, never as markup', async () => {
    const { api } = fakeApi(
      reply({ reply: 'Try <img src=x onerror=alert(1)> now [S1].' }),
    )
    render(<AskChat me={PRIYA} api={api} />)

    send('Anything?')
    const answer = await lastAnswer()

    expect(answer.querySelector('img')).toBeNull()
    expect(answer).toHaveTextContent('<img src=x onerror=alert(1)>')
  })
})
