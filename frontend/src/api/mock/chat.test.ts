import { ApiError } from '@/api/client'
import { mockChatApi } from '@/api/mock/chat'
import { mockSession, setMockLatencyScale } from '@/api/mock/backend'

beforeAll(() => setMockLatencyScale(0))
afterAll(() => setMockLatencyScale(1))

describe('mockChatApi', () => {
  it('cites each source inline and keeps the conversation going', async () => {
    const first = await mockChatApi.send({
      message: 'What is the returns window?',
      session_id: null,
    })
    const next = await mockChatApi.send({
      message: 'And for Harbor Lane?',
      session_id: first.session_id,
    })

    expect(first.citations.length).toBeGreaterThan(0)
    for (const c of first.citations) expect(first.reply).toContain(`[${c.marker}]`)
    expect(next.session_id).toBe(first.session_id)
  })

  it('rejects a session that belongs to someone else', async () => {
    const theirs = await mockChatApi.send({
      message: 'Is dock 3 open?',
      session_id: null,
    })
    const before = mockSession.get()
    mockSession.set('arun@example.com')
    try {
      await expect(
        mockChatApi.send({
          message: 'What did they ask?',
          session_id: theirs.session_id,
        }),
      ).rejects.toEqual(new ApiError(404, 'No such chat session for this user.'))
    } finally {
      mockSession.set(before)
    }
  })
})
