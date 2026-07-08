import { apiFetch } from '@/shared/api/client'
import type { SupportHistoryOut, SupportViewOut } from '@/shared/api/types'

export function getSupportView() {
  return apiFetch<SupportViewOut>('/support')
}

export function getSupportHistory() {
  return apiFetch<SupportHistoryOut>('/support/history')
}
