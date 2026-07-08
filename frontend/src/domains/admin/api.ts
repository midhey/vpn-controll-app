import { apiFetch } from '@/shared/api/client'
import type {
  AdminServerCreateIn,
  AdminServerOut,
  AdminServerUpdateIn,
  AdminUserCreateIn,
  AdminUserOut,
  AdminUserUpdateIn,
  AgentPeerOut,
  AuditLogOut,
  ContributionCreateIn,
  ContributionOut,
  DeviceOut,
  ResetPasswordIn,
  SetupJobCreateIn,
  SetupJobEventOut,
  SetupJobOut,
  SupportSettingsOut,
  SupportSettingsUpdateIn,
} from '@/shared/api/types'

export const adminApi = {
  users: {
    list: () => apiFetch<AdminUserOut[]>('/admin/users'),
    create: (payload: AdminUserCreateIn) =>
      apiFetch<AdminUserOut, AdminUserCreateIn>('/admin/users', { method: 'POST', body: payload }),
    get: (userId: string) => apiFetch<AdminUserOut>(`/admin/users/${userId}`),
    update: (userId: string, payload: AdminUserUpdateIn) =>
      apiFetch<AdminUserOut, AdminUserUpdateIn>(`/admin/users/${userId}`, {
        method: 'PATCH',
        body: payload,
      }),
    resetPassword: (userId: string, payload: ResetPasswordIn) =>
      apiFetch<{ ok: boolean }, ResetPasswordIn>(`/admin/users/${userId}/reset-password`, {
        method: 'POST',
        body: payload,
      }),
    disable: (userId: string) =>
      apiFetch<AdminUserOut>(`/admin/users/${userId}/disable`, { method: 'POST' }),
    enable: (userId: string) =>
      apiFetch<AdminUserOut>(`/admin/users/${userId}/enable`, { method: 'POST' }),
    devices: (userId: string) => apiFetch<DeviceOut[]>(`/admin/users/${userId}/devices`),
    contributions: (userId: string) =>
      apiFetch<ContributionOut[]>(`/admin/users/${userId}/support-contributions`),
    recordContribution: (userId: string, payload: ContributionCreateIn) =>
      apiFetch<ContributionOut, ContributionCreateIn>(
        `/admin/users/${userId}/support-contributions`,
        { method: 'POST', body: payload },
      ),
  },
  servers: {
    list: () => apiFetch<AdminServerOut[]>('/admin/servers'),
    create: (payload: AdminServerCreateIn) =>
      apiFetch<AdminServerOut, AdminServerCreateIn>('/admin/servers', {
        method: 'POST',
        body: payload,
      }),
    get: (serverId: string) => apiFetch<AdminServerOut>(`/admin/servers/${serverId}`),
    update: (serverId: string, payload: AdminServerUpdateIn) =>
      apiFetch<AdminServerOut, AdminServerUpdateIn>(`/admin/servers/${serverId}`, {
        method: 'PATCH',
        body: payload,
      }),
    healthCheck: (serverId: string) =>
      apiFetch<AdminServerOut>(`/admin/servers/${serverId}/health-check`, { method: 'POST' }),
    peers: (serverId: string) => apiFetch<AgentPeerOut[]>(`/admin/servers/${serverId}/peers`),
    disable: (serverId: string) =>
      apiFetch<AdminServerOut>(`/admin/servers/${serverId}/disable`, { method: 'POST' }),
    enable: (serverId: string) =>
      apiFetch<AdminServerOut>(`/admin/servers/${serverId}/enable`, { method: 'POST' }),
  },
  setupJobs: {
    list: () => apiFetch<SetupJobOut[]>('/admin/setup-jobs'),
    create: (payload: SetupJobCreateIn) =>
      apiFetch<SetupJobOut, SetupJobCreateIn>('/admin/setup-jobs', {
        method: 'POST',
        body: payload,
      }),
    get: (jobId: string) => apiFetch<SetupJobOut>(`/admin/setup-jobs/${jobId}`),
    start: (jobId: string) =>
      apiFetch<SetupJobOut>(`/admin/setup-jobs/${jobId}/start`, { method: 'POST' }),
    cancel: (jobId: string) =>
      apiFetch<SetupJobOut>(`/admin/setup-jobs/${jobId}/cancel`, { method: 'POST' }),
    events: (jobId: string) =>
      apiFetch<SetupJobEventOut[]>(`/admin/setup-jobs/${jobId}/events`),
  },
  support: {
    getSettings: () => apiFetch<SupportSettingsOut>('/admin/support-settings'),
    updateSettings: (payload: SupportSettingsUpdateIn) =>
      apiFetch<SupportSettingsOut, SupportSettingsUpdateIn>('/admin/support-settings', {
        method: 'PATCH',
        body: payload,
      }),
  },
  audit: {
    list: (limit = 100) => apiFetch<AuditLogOut[]>(`/admin/audit-logs?limit=${limit}`),
  },
}
