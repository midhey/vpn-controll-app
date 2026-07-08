import { apiFetch } from '@/shared/api/client'
import type { DeviceCreateIn, DeviceCreateOut, DeviceOut, IssueResultOut } from '@/shared/api/types'

export function listDevices() {
  return apiFetch<DeviceOut[]>('/devices')
}

export function createDevice(payload: DeviceCreateIn) {
  return apiFetch<DeviceCreateOut, DeviceCreateIn>('/devices', { method: 'POST', body: payload })
}

export function getDevice(deviceId: string) {
  return apiFetch<DeviceOut>(`/devices/${deviceId}`)
}

export function revokeDevice(deviceId: string) {
  return apiFetch<DeviceOut>(`/devices/${deviceId}`, { method: 'DELETE' })
}

export function getIssueResult(deviceId: string) {
  return apiFetch<IssueResultOut>(`/devices/${deviceId}/issue-result`)
}
