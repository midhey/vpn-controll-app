import { apiFetch } from '@/shared/api/client'
import type { LoginIn, SessionOut, UserOut } from '@/shared/api/types'

export function login(payload: LoginIn) {
  return apiFetch<SessionOut, LoginIn>('/auth/login', { method: 'POST', body: payload })
}

export function logout() {
  return apiFetch<Record<string, unknown>>('/auth/logout', { method: 'POST' })
}

export function session() {
  return apiFetch<SessionOut>('/auth/session')
}

export function me() {
  return apiFetch<UserOut>('/me')
}
