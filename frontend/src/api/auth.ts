import { apiGet, apiPost } from '@/api/client'

export interface Grant {
  scope_path: string
  access: 'read' | 'write'
  layer: 'org' | 'team' | 'personal'
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

// A full-page navigation, not fetch: the backend redirects to Microsoft Entra ID.
export const SSO_LOGIN_URL = '/api/v1/auth/login'

export const getMe = (signal?: AbortSignal) => apiGet<Me>('/api/v1/auth/me', { signal })

export const getAuthConfig = (signal?: AbortSignal) =>
  apiGet<AuthConfig>('/api/v1/auth/config', { signal })

export const devLogin = (email: string, name: string) =>
  apiPost<Me>('/api/v1/auth/dev-login', { email, name })

export const logout = () => apiPost<void>('/api/v1/auth/logout')
