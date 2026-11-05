import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ApiError } from '@/api/client'
import { meOf } from '@/api/mock/auth'
import { userByEmail } from '@/api/mock/backend'
import type {
  ReflectApi,
  ReflectLayer,
  ReflectRequest,
  ReflectResponse,
} from '@/api/reflect'
import AskReflect from '@/components/ask/AskReflect'
import { clearReflections } from '@/components/ask/reflectStore'

/** Priya, as the mock signs her in: org, her team (ops) and her own space. */
const PRIYA = meOf(userByEmail('priya@example.com')!)

afterEach(() => clearReflections())

function layer(over: Partial<ReflectLayer>): ReflectLayer {
  return {
    layer: 'org',
    scope: 'org',
    status: 'applies',
    answer: 'The discount is 10%.',
    evidence: ['Harbor Basics max discount is 10%'],
    error: null,
    trace_id: 'tr',
    ...over,
  }
}

const ANSWER: ReflectResponse = {
  layers: [
    layer({}),
    layer({
      layer: 'team',
      scope: 'org/team/ops',
      status: 'overridden',
      answer: 'The discount is 20%.',
      evidence: ['Harbor Basics max discount is 20%'],
    }),
    layer({
      layer: 'personal',
      scope: 'org/user/u-0001',
      status: 'overridden',
      answer: 'The discount is 12%.',
      evidence: ['Harbor Basics max discount is 12%', 'Acme lead time is 18 days'],
    }),
  ],
  applies: 'org',
  scopes: ['org', 'org/team/ops', 'org/user/u-0001'],
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
const layerCard = (answer: HTMLElement, name: string) =>
  within(answer).getByRole('region', { name: `${name} reflection` })

describe('AskReflect', () => {
  it('says the answer is the model’s conclusion and that nothing is saved', () => {
    render(<AskReflect me={PRIYA} api={fakeApi().api} />)

    expect(screen.getByText(/nothing is saved/i)).toBeInTheDocument()
    expect(screen.getByText(/check it against the evidence/i)).toBeInTheDocument()
  })

  it('shows each layer’s own reflection and evidence, without precedence labels', async () => {
    const { api, requests } = fakeApi()
    render(<AskReflect me={PRIYA} api={api} />)

    ask('Harbor Basics discount?')

    await waitFor(() => expect(answers()).toHaveLength(1))
    expect(requests).toEqual([{ question: 'Harbor Basics discount?', scopes: [] }])
    const answer = answers()[0]!
    expect(layerCard(answer, 'Org')).toHaveTextContent('The discount is 10%.')
    expect(layerCard(answer, 'Team')).toHaveTextContent('The discount is 20%.')
    const personal = layerCard(answer, 'Personal')
    const evidence = within(personal).getByRole('list', { name: 'Evidence' })
    expect(within(evidence).getAllByRole('listitem')).toHaveLength(2)
    expect(answer).not.toHaveTextContent(/Applies|Overridden|org > team > personal/)
  })

  it('a failed layer shows its error', async () => {
    const { api } = fakeApi({
      ...ANSWER,
      layers: [
        layer({}),
        layer({
          layer: 'team',
          scope: 'org/team/ops',
          status: 'failed',
          answer: null,
          evidence: [],
          error: 'timeout',
        }),
      ],
    })
    render(<AskReflect me={PRIYA} api={api} />)

    ask('Harbor Basics discount?')

    await waitFor(() => expect(answers()).toHaveLength(1))
    expect(layerCard(answers()[0]!, 'Team')).toHaveTextContent('timeout')
  })

  it('each question stands alone, newest first', async () => {
    const { api, requests } = fakeApi(ANSWER, {
      ...ANSWER,
      layers: [layer({ answer: 'Guardrails are 15%, 12% and 8%.' })],
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
})
