import { useEffect, useState } from 'react'

/** The hash split into segments: "#/ask/chat" -> ["ask", "chat"]. */
function segments(): string[] {
  return window.location.hash.replace(/^#\/?/, '').split('/')
}

function pick<T extends string>(
  name: string | undefined,
  routes: readonly T[],
  fallback: T,
): T {
  return name !== undefined && (routes as readonly string[]).includes(name)
    ? (name as T)
    : fallback
}

/** Re-reads `read()` whenever the hash changes. */
function useHashValue<T>(read: () => T, deps: readonly unknown[]): T {
  const [value, setValue] = useState<T>(read)

  useEffect(() => {
    const onChange = () => setValue(read())
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
    // `read` is rebuilt each render from `deps`, which are what matter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return value
}

/**
 * The page named first in the URL hash (#/ask, or #/ask/chat), or `fallback`
 * for anything unknown. `routes` must be stable (a module-level constant),
 * since it is an effect dependency.
 */
export function useHashRoute<T extends string>(routes: readonly T[], fallback: T): T {
  return useHashValue(() => pick(segments()[0], routes, fallback), [routes, fallback])
}

/**
 * The mode named second in the URL hash (#/ask/chat -> "chat"), or `fallback`.
 * `modes` must be stable, like `useHashRoute`'s routes.
 */
export function useHashSubRoute<T extends string>(modes: readonly T[], fallback: T): T {
  return useHashValue(() => pick(segments()[1], modes, fallback), [modes, fallback])
}
