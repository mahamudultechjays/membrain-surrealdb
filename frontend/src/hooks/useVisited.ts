import { useState } from 'react'

/**
 * Every view shown so far, in the order first shown. A view joins on its first
 * visit and stays, so views nobody opens are never mounted (see KeepAlive).
 */
export function useVisited<T>(current: T): T[] {
  const [seen, setSeen] = useState<T[]>([current])
  if (seen.includes(current)) return seen
  // Updating during render is React's pattern for state derived from props.
  const next = [...seen, current]
  setSeen(next)
  return next
}
