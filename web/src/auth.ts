import { reactive } from 'vue'
import { apiGet, apiPost } from './api'
import { setCsrfToken } from './session'

export interface AuthStatus {
  initialized: boolean
  authenticated: boolean
  must_change_password: boolean
  username: string
  csrf_token: string
}

export const authState = reactive<AuthStatus>({
  initialized: false,
  authenticated: false,
  must_change_password: false,
  username: '',
  csrf_token: '',
})

let loaded = false

function applyStatus(status: Partial<AuthStatus>): AuthStatus {
  Object.assign(authState, {
    initialized: status.initialized ?? true,
    authenticated: !!status.authenticated,
    must_change_password: !!status.must_change_password,
    username: status.username || '',
    csrf_token: status.csrf_token || '',
  })
  setCsrfToken(authState.csrf_token)
  loaded = true
  return authState
}

export async function refreshAuth(force = false): Promise<AuthStatus> {
  if (loaded && !force) return authState
  return applyStatus(await apiGet<AuthStatus>('/auth/status'))
}

export async function login(username: string, password: string): Promise<AuthStatus> {
  return applyStatus(await apiPost<AuthStatus>('/auth/login', { username, password }))
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<AuthStatus> {
  return applyStatus(await apiPost<AuthStatus>('/auth/change-password', {
    current_password: currentPassword,
    new_password: newPassword,
  }))
}

export async function logout(): Promise<void> {
  await apiPost('/auth/logout', {})
  applyStatus({ initialized: true, authenticated: false })
}
