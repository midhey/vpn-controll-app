import { apiFetch } from '@/shared/api/client'
import type { ServerOut } from '@/shared/api/types'

export function listServers() {
  return apiFetch<ServerOut[]>('/servers')
}

export function getServer(serverId: string) {
  return apiFetch<ServerOut>(`/servers/${serverId}`)
}
