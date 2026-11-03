import type { AdminApi, UserGrants } from '@/api/admin'
import { ApiError } from '@/api/client'
import {
  MOCK_ADMINS,
  MOCK_REGISTERED,
  MOCK_USERS,
  ORG_PATH,
  currentUser,
  delay,
  ownerOf,
  userByEmail,
  type MockUser,
} from '@/api/mock/backend'

const SCOPE_PATH = /^[a-z0-9][a-z0-9_-]*(\/[a-z0-9][a-z0-9_-]*)*$/

function requireAdmin() {
  if (!MOCK_ADMINS.has(currentUser().email)) {
    throw new ApiError(403, 'Admins only.')
  }
}

const out = (user: MockUser): UserGrants => ({
  email: user.email,
  name: user.name,
  is_admin: MOCK_ADMINS.has(user.email),
  grants: user.grants.map((g) => ({ ...g, owner: ownerOf(g.scope_path) })),
})

/** The same checks as the backend: a lowercase path inside the org tree. */
function underOrg(raw: string): string {
  const path = raw.trim().replace(/^\/+|\/+$/g, '')
  if (!SCOPE_PATH.test(path)) {
    throw new ApiError(422, 'Use a lowercase path like org/team/ops.')
  }
  if (path !== ORG_PATH && !path.startsWith(ORG_PATH + '/')) {
    throw new ApiError(422, `Scopes must be under ${ORG_PATH}.`)
  }
  return path
}

/** Register a path and any missing parent, as AgentMemoryScopeRegistry.ensure does. */
function ensure(path: string) {
  const parts = path.split('/')
  parts.forEach((_, i) => MOCK_REGISTERED.add(parts.slice(0, i + 1).join('/')))
}

export const mockAdminApi: AdminApi = {
  async users(signal) {
    await delay(150, signal)
    requireAdmin()
    return MOCK_USERS.map(out)
  },

  async grant(email, { scope_path, access, layer, name }) {
    await delay(150)
    requireAdmin()
    const path = underOrg(scope_path)
    const key = email.trim().toLowerCase()
    let user = userByEmail(key)
    if (!user) {
      user = { email: key, name: name?.trim() || key, grants: [] }
      MOCK_USERS.push(user)
    }
    ensure(path)
    const existing = user.grants.find((g) => g.scope_path === path)
    if (existing) Object.assign(existing, { access, layer })
    else user.grants.push({ scope_path: path, access, layer })
    return out(user)
  },

  async revoke(email, scopePath) {
    await delay(150)
    requireAdmin()
    const user = userByEmail(email)
    const index = user?.grants.findIndex((g) => g.scope_path === scopePath) ?? -1
    if (!user || index < 0) {
      throw new ApiError(404, 'That user does not hold that scope.')
    }
    user.grants.splice(index, 1)
  },

  async scopes(prefix, signal) {
    await delay(150, signal)
    requireAdmin()
    const root = underOrg(prefix ?? ORG_PATH)
    return [...MOCK_REGISTERED].filter((p) => p.startsWith(root)).sort()
  },

  async registerScope(path) {
    await delay(150)
    requireAdmin()
    ensure(underOrg(path))
  },
}
