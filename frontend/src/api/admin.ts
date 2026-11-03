import type { Access, Grant, GrantLayer } from '@/api/auth'
import { apiDelete, apiGet, apiPost } from '@/api/client'
import { USE_MOCK_API } from '@/api/config'
import { mockAdminApi } from '@/api/mock/admin'

// Mirrors backend/app/schemas/admin.py. Every call needs an admin session.

export interface UserGrants {
  email: string
  name: string
  is_admin: boolean
  grants: Grant[]
}

export interface GrantInput {
  scope_path: string
  access: Access
  layer: GrantLayer
  /** Only used for someone who has never signed in. */
  name?: string | null
}

export interface AdminApi {
  users(signal?: AbortSignal): Promise<UserGrants[]>
  /** Registers the scope in Agent Memory first if it is new. Returns the user. */
  grant(email: string, grant: GrantInput): Promise<UserGrants>
  revoke(email: string, scopePath: string): Promise<void>
  /** Registered scopes under the org scope (or `prefix`). */
  scopes(prefix?: string, signal?: AbortSignal): Promise<string[]>
  registerScope(path: string): Promise<void>
}

const userPath = (email: string) => `/api/v1/admin/users/${encodeURIComponent(email)}`

export const httpAdminApi: AdminApi = {
  users: async (signal) =>
    (await apiGet<{ users: UserGrants[] }>('/api/v1/admin/users', { signal })).users,
  grant: (email, grant) => apiPost<UserGrants>(`${userPath(email)}/grants`, grant),
  revoke: (email, scopePath) =>
    apiDelete(`${userPath(email)}/grants?scope_path=${encodeURIComponent(scopePath)}`),
  scopes: async (prefix, signal) => {
    const query = prefix ? `?prefix=${encodeURIComponent(prefix)}` : ''
    return (
      await apiGet<{ scopes: string[] }>(`/api/v1/admin/scopes${query}`, { signal })
    ).scopes
  },
  registerScope: async (path) => {
    await apiPost<{ scopes: string[] }>('/api/v1/admin/scopes', { path })
  },
}

export const adminApi: AdminApi = USE_MOCK_API ? mockAdminApi : httpAdminApi
