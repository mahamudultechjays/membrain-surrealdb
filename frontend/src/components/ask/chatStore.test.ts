import { clearChats, getChat, updateChat } from '@/components/ask/chatStore'

const OWNER = 'priya@example.com'

afterEach(() => clearChats())

describe('chatStore', () => {
  it('starts empty for someone who has not chatted', () => {
    expect(getChat(OWNER)).toEqual({ turns: [], sessionId: null })
  })

  it('keeps each person’s conversation apart', () => {
    updateChat(OWNER, (s) => ({ ...s, sessionId: 'sess-1' }))

    expect(getChat(OWNER).sessionId).toBe('sess-1')
    expect(getChat('arun@example.com').sessionId).toBeNull()
  })

  it('returns the same object until something changes, as React needs', () => {
    const first = getChat(OWNER)

    expect(getChat(OWNER)).toBe(first)
    updateChat(OWNER, (s) => ({ ...s, sessionId: 'sess-1' }))
    expect(getChat(OWNER)).not.toBe(first)
  })

  it('is saved for this browser tab, so a reload restores it', async () => {
    updateChat(OWNER, () => ({
      sessionId: 'sess-1',
      turns: [{ id: 't1', question: 'Where does Acme ship?', status: 'cancelled' }],
    }))

    vi.resetModules()
    const reloaded = await import('@/components/ask/chatStore')

    expect(reloaded.getChat(OWNER).sessionId).toBe('sess-1')
    expect(reloaded.getChat(OWNER).turns[0]?.question).toBe('Where does Acme ship?')
  })

  it('a question still waiting when the page reloaded comes back as interrupted', async () => {
    updateChat(OWNER, () => ({
      sessionId: null,
      turns: [{ id: 't1', question: 'Slow one?', status: 'loading' }],
    }))

    vi.resetModules()
    const reloaded = await import('@/components/ask/chatStore')

    expect(reloaded.getChat(OWNER).turns[0]?.status).toBe('cancelled')
  })

  it('clearChats forgets everyone, in memory and in storage', async () => {
    updateChat(OWNER, (s) => ({ ...s, sessionId: 'sess-1' }))

    clearChats()
    vi.resetModules()
    const reloaded = await import('@/components/ask/chatStore')

    expect(getChat(OWNER).sessionId).toBeNull()
    expect(reloaded.getChat(OWNER).sessionId).toBeNull()
  })
})
