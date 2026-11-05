import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ApiError } from '@/api/client'
import { meOf } from '@/api/mock/auth'
import { userByEmail } from '@/api/mock/backend'
import type { ReflectApi, ReflectRequest, ReflectResponse } from '@/api/reflect'
import AskReflect from '@/components/ask/AskReflect'
import { ownScope } from '@/components/ask/layers'
import { clearReflections } from '@/components/ask/reflectStore'

/** Priya, as the mock signs her in: org, her team (ops) and her own space. */
const PRIYA = meOf(userByEmail('priya@example.com')!)

afterEach(() => clearReflections())

const ANSWER: ReflectResponse = {
  answer: 'Acme Logistics is the only carrier, and its lead time is rising.',
  evidence: ['Acme Logistics ships to Reno', 'Acme lead time is 18 days (up from 10)'],
  scopes: ['org', 'org/user/u-0001'],
  trace_id: 'tr-1',
}

function fakeApi(...answers: (ReflectResponse | Error)[]) {
  const requests: ReflectRequest[] = []
  const api: ReflectApi = {
    ask: (request) => {
      requests.push(request)
      const next = answers.shift() ?? ANSWER
      return next instanceof Error ? Promise.reject(next) : Promise.resolve(next)
    },
  }
  return { api, requests }
}

function ask(text: string) {
  fireEvent.change(screen.getByLabelText('Question'), { target: { value: text } })
  fireEvent.click(screen.getByRole('button', { name: 'Reflect' }))
}

const answers = () => screen.queryAllByRole('article', { name: /^Reflection on/ })

describe('AskReflect', () => {
  it('says the answer is the model’s conclusion and that nothing is saved', () => {
    render(<AskReflect me={PRIYA} api={fakeApi().api} />)

    expect(screen.getByText(/nothing is saved/i)).toBeInTheDocument()
    expect(screen.getByText(/check it against the evidence/i)).toBeInTheDocument()
  })

  it('reflects on Priya’s own space by default, and shows the answer with its evidence', async () => {
    const { api, requests } = fakeApi()
    render(<AskReflect me={PRIYA} api={api} />)

    ask('What do we know about carriers?')

    await waitFor(() => expect(answers()).toHaveLength(1))
    expect(requests).toEqual([
      { question: 'What do we know about carriers?', scopes: [ownScope(PRIYA.grants)] },
    ])
    const answer = answers()[0]!
    expect(answer).toHaveTextContent('Acme Logistics is the only carrier')
    const evidence = within(answer).getByRole('list', { name: 'Evidence' })
    expect(within(evidence).getAllByRole('listitem')).toHaveLength(2)
    expect(
      within(evidence).getByText('Acme lead time is 18 days (up from 10)'),
    ).toBeInTheDocument()
  })

  it('each question stands alone, newest first', async () => {
    const { api, requests } = fakeApi(ANSWER, {
      ...ANSWER,
      answer: 'Guardrails are 15%, 12% and 8%.',
    })
    render(<AskReflect me={PRIYA} api={api} />)

    ask('Carriers?')
    await waitFor(() => expect(answers()).toHaveLength(1))
    ask('Guardrails?')
    await waitFor(() => expect(answers()).toHaveLength(2))

    expect(requests.map((r) => r.question)).toEqual(['Carriers?', 'Guardrails?'])
    expect(answers()[0]).toHaveTextContent('Guardrails are 15%, 12% and 8%.')
  })

  it('reports a failure without losing the question', async () => {
    const { api } = fakeApi(new ApiError(503, 'Agent Memory call failed: down'))
    render(<AskReflect me={PRIYA} api={api} />)

    ask('Carriers?')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Agent Memory call failed: down',
    )
    expect(screen.getByText('Carriers?')).toBeInTheDocument()
  })

  it('keeps the answers when the page is left and reopened, until cleared', async () => {
    const { api } = fakeApi()
    const first = render(<AskReflect me={PRIYA} api={api} />)
    ask('Carriers?')
    await waitFor(() => expect(answers()).toHaveLength(1))

    first.unmount()
    render(<AskReflect me={PRIYA} api={api} />)
    expect(answers()).toHaveLength(1)

    fireEvent.click(screen.getByRole('button', { name: 'Clear' }))
    expect(answers()).toHaveLength(0)
  })

  it('an answer with no evidence says so', async () => {
    const { api } = fakeApi({ ...ANSWER, evidence: [] })
    render(<AskReflect me={PRIYA} api={api} />)

    ask('Unknown?')

    await waitFor(() => expect(answers()).toHaveLength(1))
    expect(answers()[0]).toHaveTextContent('No evidence returned.')
  })
})
