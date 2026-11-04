import { act, renderHook } from '@testing-library/react'
import { useHashRoute, useHashSubRoute } from '@/hooks/useHashRoute'

const ROUTES = ['capture', 'ask'] as const
const MODES = ['search', 'chat'] as const

function go(hash: string) {
  act(() => {
    window.location.hash = hash
    window.dispatchEvent(new HashChangeEvent('hashchange'))
  })
}

afterEach(() => {
  window.location.hash = ''
})

describe('useHashRoute', () => {
  it('matches the page by the first segment, so #/ask/chat is the ask page', () => {
    const { result } = renderHook(() => useHashRoute(ROUTES, 'capture'))

    go('#/ask/chat')

    expect(result.current).toBe('ask')
  })

  it('falls back for an unknown page', () => {
    const { result } = renderHook(() => useHashRoute(ROUTES, 'capture'))

    go('#/nowhere')

    expect(result.current).toBe('capture')
  })
})

describe('useHashSubRoute', () => {
  it('reads the second segment and follows changes', () => {
    const { result } = renderHook(() => useHashSubRoute(MODES, 'search'))

    go('#/ask/chat')
    expect(result.current).toBe('chat')
    go('#/ask/search')
    expect(result.current).toBe('search')
  })

  it('defaults when there is no second segment', () => {
    go('#/ask')

    const { result } = renderHook(() => useHashSubRoute(MODES, 'search'))

    expect(result.current).toBe('search')
  })
})
