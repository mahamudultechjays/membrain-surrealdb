import { ApiError } from '@/api/client'

// In-browser stand-in for the backend on feat/capture-ak-scoping-api. It keeps
// the same rules (signed-in user, scope grants, preview cache, error statuses)
// so the UI behaves the same once it calls the real API. State lives for the
// page's lifetime, which also mimics the backend's in-process preview cache.

export type MockLayerName = 'org' | 'team' | 'personal'

export interface MockGrant {
  scope_path: string
  access: 'read' | 'write'
  layer: MockLayerName
}

export interface MockUser {
  email: string
  name: string
  grants: MockGrant[]
}

/** The mock's org scope; the real backend's default is org/spreetail. */
export const ORG_PATH = 'org'
export const USER_ROOT = 'org/user'

const read = (scope_path: string, layer: MockLayerName): MockGrant => ({
  scope_path,
  access: 'read',
  layer,
})
const own = (scope_path: string): MockGrant => ({
  scope_path,
  access: 'write',
  layer: 'personal',
})

// Mutable: admins grant and revoke, and a dev login adds a user.
export const MOCK_USERS: MockUser[] = [
  {
    email: 'priya@example.com',
    name: 'Priya',
    grants: [read('org', 'org'), read('org/team/ops', 'team'), own('org/user/u-0001')],
  },
  {
    email: 'arun@example.com',
    name: 'Arun',
    grants: [read('org', 'org'), read('org/team/eng', 'team'), own('org/user/u-0002')],
  },
  {
    email: 'deena@example.com',
    name: 'Deena',
    grants: [read('org', 'org'), read('org/team/ops', 'team'), own('org/user/u-0003')],
  },
]

export const MOCK_ADMINS = new Set(['priya@example.com'])

/** Scopes registered in the mock Agent Memory context. */
export const MOCK_REGISTERED = new Set([
  'org',
  'org/team',
  'org/user',
  ...MOCK_USERS.flatMap((u) => u.grants.map((g) => g.scope_path)),
])

/** Who the mock session belongs to; null when signed out. Priya is an admin. */
let signedIn: string | null = 'priya@example.com'

export const mockSession = {
  get: () => signedIn,
  set: (email: string | null) => {
    signedIn = email
  },
}

export function userByEmail(email: string): MockUser | undefined {
  return MOCK_USERS.find((u) => u.email === email.trim().toLowerCase())
}

/** Whose personal scope a path is, as AccessService.owners decides it. */
export function ownerOf(path: string): string | null {
  for (const user of MOCK_USERS) {
    if (user.grants.some((g) => g.layer === 'personal' && g.scope_path === path)) {
      return user.name
    }
  }
  return null
}

/** The signed-in user, or a 401 like the backend's session check. */
export function currentUser(): MockUser {
  const user = signedIn ? userByEmail(signedIn) : undefined
  if (!user) throw new ApiError(401, 'Not signed in.')
  return user
}

/** A record recall can find: a stored fact or a document passage. */
export interface MockRecord {
  id: string
  area: string
  kind: 'attribute' | 'entity' | 'chunk'
  text: string
}

let nextId = 1
export const newId = (prefix: string) =>
  `${prefix}_${(nextId++).toString(16).padStart(6, '0')}`

const SEED: Omit<MockRecord, 'id'>[] = [
  {
    area: 'org',
    kind: 'chunk',
    text: 'Customers may return items within 30 days of delivery.',
  },
  { area: 'org', kind: 'attribute', text: 'returns policy · window_days = 30' },
  { area: 'org', kind: 'attribute', text: 'returns policy · restocking_fee = 10%' },
  { area: 'org/team/ops', kind: 'attribute', text: 'receiving · sla_hours = 4' },
  {
    area: 'org/team/ops',
    kind: 'attribute',
    text: 'acme logistics · lead_time_days = 10',
  },
  { area: 'org/team/eng', kind: 'attribute', text: 'checkout service · on_call = Arun' },
  {
    area: 'org/user/u-0001',
    kind: 'attribute',
    text: 'reno warehouse · dock_3_status = closed',
  },
  {
    area: 'org/user/u-0001',
    kind: 'attribute',
    text: 'returns policy · window_days = 60',
  },
  {
    area: 'org/user/u-0002',
    kind: 'attribute',
    text: 'kestrel launch · date = 12 November',
  },
  {
    area: 'org/user/u-0003',
    kind: 'attribute',
    text: 'acme logistics · contact = Nina Okafor',
  },
]

export const records: MockRecord[] = SEED.map((r) => ({ ...r, id: newId(r.kind) }))

let latencyScale = 1

/** Scale every mock delay; tests pass 0 so they don't wait on fake network time. */
export function setMockLatencyScale(scale: number) {
  latencyScale = scale
}

/** Waits like a network call would, and stops early if the caller aborts. */
export function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(abortError())
    const timer = setTimeout(resolve, ms * latencyScale)
    signal?.addEventListener(
      'abort',
      () => {
        clearTimeout(timer)
        reject(abortError())
      },
      { once: true },
    )
  })
}

function abortError() {
  return new DOMException('The operation was aborted.', 'AbortError')
}

export const traceId = () =>
  `t-${Math.random().toString(16).slice(2, 14).padEnd(12, '0')}`
