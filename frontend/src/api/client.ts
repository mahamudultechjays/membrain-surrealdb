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
    throw await errorFrom(response, `GET ${path}`)
  }
  return (await response.json()) as T
}

/** POSTs JSON (or nothing) and returns the JSON reply, or undefined for 204. */
export async function apiPost<T>(
  path: string,
  body?: unknown,
  { signal }: { signal?: AbortSignal } = {},
): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  })
  if (!response.ok) throw await errorFrom(response, `POST ${path}`)
  return (response.status === 204 ? undefined : await response.json()) as T
}

export async function apiDelete(
  path: string,
  { signal }: { signal?: AbortSignal } = {},
): Promise<void> {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: 'DELETE',
    headers: { Accept: 'application/json' },
    signal,
  })
  if (!response.ok) throw await errorFrom(response, `DELETE ${path}`)
}

/** FastAPI puts the reason in `detail`: a string, or a list of validation errors. */
async function errorFrom(response: Response, call: string): Promise<ApiError> {
  let reason = `${call} failed with ${response.status}`
  try {
    const { detail } = (await response.json()) as { detail?: unknown }
    if (typeof detail === 'string') reason = detail
    else if (Array.isArray(detail) && detail.length) {
      reason = detail.map((d: { msg?: string }) => d.msg ?? String(d)).join('; ')
    }
  } catch {
    // Not JSON: keep the generic message.
  }
  return new ApiError(response.status, reason)
}
