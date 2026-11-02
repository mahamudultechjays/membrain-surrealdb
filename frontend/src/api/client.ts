// Relative by default: Vite's dev proxy and nginx in prod both forward /api to
// the backend, so the browser stays same-origin and needs no CORS.
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

interface GetOptions {
  signal?: AbortSignal
  /** Non-2xx statuses whose JSON body is still a valid answer, e.g. a 503 readiness report. */
  acceptStatuses?: readonly number[]
}

export async function apiGet<T>(
  path: string,
  { signal, acceptStatuses = [] }: GetOptions = {},
): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { Accept: 'application/json' },
    signal,
  })
  if (!response.ok && !acceptStatuses.includes(response.status)) {
    throw new ApiError(response.status, `GET ${path} failed with ${response.status}`)
  }
  return (await response.json()) as T
}

/** POSTs JSON (or nothing) and returns the JSON reply, or undefined for 204. */
export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    const detail = await response
      .json()
      .then((data: { detail?: unknown }) =>
        typeof data.detail === 'string' ? data.detail : '',
      )
      .catch(() => '')
    throw new ApiError(
      response.status,
      detail || `POST ${path} failed with ${response.status}`,
    )
  }
  return (response.status === 204 ? undefined : await response.json()) as T
}
