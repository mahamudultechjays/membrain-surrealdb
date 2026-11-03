import { apiGet, apiPost } from '@/api/client'
import { USE_MOCK_API } from '@/api/config'
import { mockAuthApi } from '@/api/mock/auth'

// Mirrors backend/app/schemas/auth.py.

export type Access = 'read' | 'write'
export type GrantLayer = 'org' | 'team' | 'personal'

export interface Grant {
  scope_path: string
  access: Access
  layer: GrantLayer
  /** Whose space this is: the user holding it as their personal scope, else null. */
  owner?: string | null
}

export interface Me {
  email: string
  name: string
  is_admin: boolean
  grants: Grant[]
}

export interface AuthConfig {
  sso_enabled: boolean
  dev_login_enabled: boolean
}

export interface AuthApi {
  getMe(signal?: AbortSignal): Promise<Me>
  getAuthConfig(signal?: AbortSignal): Promise<AuthConfig>
  devLogin(email: string, name: string): Promise<Me>
  logout(): Promise<void>
}

// A full-page navigation, not fetch: the backend redirects to Microsoft Entra ID.
export const SSO_LOGIN_URL = '/api/v1/auth/login'

export const httpAuthApi: AuthApi = {
  getMe: (signal) => apiGet<Me>('/api/v1/auth/me', { signal }),
  getAuthConfig: (signal) => apiGet<AuthConfig>('/api/v1/auth/config', { signal }),
  devLogin: (email, name) => apiPost<Me>('/api/v1/auth/dev-login', { email, name }),
  logout: () => apiPost<void>('/api/v1/auth/logout'),
}

export const authApi: AuthApi = USE_MOCK_API ? mockAuthApi : httpAuthApi

export const getMe = (signal?: AbortSignal) => authApi.getMe(signal)
export const getAuthConfig = (signal?: AbortSignal) => authApi.getAuthConfig(signal)
export const devLogin = (email: string, name: string) => authApi.devLogin(email, name)
export const logout = () => authApi.logout()
