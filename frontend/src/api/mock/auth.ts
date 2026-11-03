import type { AuthApi, Me } from '@/api/auth'
import {
  MOCK_ADMINS,
  MOCK_REGISTERED,
  MOCK_USERS,
  ORG_PATH,
  USER_ROOT,
  currentUser,
  delay,
  mockSession,
  ownerOf,
  userByEmail,
  type MockUser,
} from '@/api/mock/backend'

export const meOf = (user: MockUser): Me => ({
  email: user.email,
  name: user.name,
  is_admin: MOCK_ADMINS.has(user.email),
  grants: user.grants.map((g) => ({ ...g, owner: ownerOf(g.scope_path) })),
})

/** 'Hari Kumar' -> org/user/hari_kumar, as the backend names personal scopes. */
function personalScope(name: string, email: string) {
  const words = name.toLowerCase().match(/[a-z0-9]+/g) ?? []
  const slug =
    words.length > 1
      ? `${words[0]}_${words[words.length - 1]}`
      : (words[0] ?? email.split('@')[0] ?? 'user')
  return `${USER_ROOT}/${slug}`
}

export const mockAuthApi: AuthApi = {
  async getMe(signal) {
    await delay(100, signal)
    return meOf(currentUser())
  },

  async getAuthConfig(signal) {
    await delay(100, signal)
    return { sso_enabled: false, dev_login_enabled: true }
  },

  // Like the backend's first sign-in: a personal scope to write, and org to read.
  async devLogin(email, name) {
    await delay(150)
    const key = email.trim().toLowerCase()
    let user = userByEmail(key)
    if (!user) {
      const personal = personalScope(name, key)
      MOCK_REGISTERED.add(personal)
      user = {
        email: key,
        name: name.trim(),
        grants: [
          { scope_path: ORG_PATH, access: 'read', layer: 'org' },
          { scope_path: personal, access: 'write', layer: 'personal' },
        ],
      }
      MOCK_USERS.push(user)
    }
    mockSession.set(user.email)
    return meOf(user)
  },

  async logout() {
    await delay(100)
    mockSession.set(null)
  },
}
