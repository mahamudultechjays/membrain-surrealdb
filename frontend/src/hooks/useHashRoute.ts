import { useEffect, useState } from 'react'

function routeFrom<T extends string>(routes: readonly T[], fallback: T): T {
  const name = window.location.hash.replace(/^#\/?/, '')
  return (routes as readonly string[]).includes(name) ? (name as T) : fallback
}

/**
 * The page named in the URL hash (#/ask), or `fallback` for anything unknown.
 * `routes` must be stable (a module-level constant), since it is an effect dependency.
 */
export function useHashRoute<T extends string>(routes: readonly T[], fallback: T): T {
  const [route, setRoute] = useState<T>(() => routeFrom(routes, fallback))

  useEffect(() => {
    const onChange = () => setRoute(routeFrom(routes, fallback))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [routes, fallback])

  return route
}
