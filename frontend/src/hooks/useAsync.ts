import { useEffect, useState } from 'react'

export type AsyncState<T> =
  | { status: 'loading' }
  | { status: 'success'; data: T }
  | { status: 'error'; error: Error }

/**
 * Runs `load` on mount and aborts it on unmount, so a slow response can never
 * set state on an unmounted component. `load` must be stable (module-level or
 * memoised), since it is the effect's only dependency.
 */
export function useAsync<T>(load: (signal: AbortSignal) => Promise<T>): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ status: 'loading' })

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
      .then((data) => setState({ status: 'success', data }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setState({
          status: 'error',
          error: error instanceof Error ? error : new Error(String(error)),
        })
      })
    return () => controller.abort()
  }, [load])

  return state
}
