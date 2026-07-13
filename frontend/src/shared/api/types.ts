export type UserRole = 'admin' | 'user'
export type DeviceStatus = 'provisioning' | 'active' | 'revoked' | 'failed'
export type ServerStatus =
  | 'draft'
  | 'setup_pending'
  | 'setup_running'
  | 'online'
  | 'warning'
  | 'offline'
  | 'disabled'
  | 'setup_failed'
export type AuthMethod = 'ssh_key' | 'password'
export type SetupJobStatus =
  | 'draft'
  | 'queued'
  | 'checking_ssh'
  | 'installing_agent'
  | 'installing_vpn'
  | 'verifying'
  | 'success'
  | 'failed'
  | 'cancelled'
export type EventLevel = 'info' | 'warning' | 'error'

export interface ApiErrorBody {
  error?: {
    code: string
    message: string
    details?: Record<string, unknown>
  }
}

export interface UserOut {
  id: string
  login: string
  display_name: string
  role: UserRole
  telegram_username?: string | null
}

export interface SessionOut {
  user: UserOut
}

export interface LoginIn {
  login: string
  password: string
}

export interface AccessOut {
  is_active: boolean
  message: string
}

export interface DeviceLimitOut {
  used: number
  limit?: number | null
  unlimited: boolean
}

export interface SupportHintOut {
  visible: boolean
  hint?: string | null
}

export interface DashboardOut {
  user: UserOut
  access: AccessOut
  device_limit: DeviceLimitOut
  support: SupportHintOut
  recent_devices: DeviceOut[]
}

export interface DeviceOut {
  id: string
  name: string
  status: DeviceStatus
  server_node_id: string
  server_name?: string | null
  client_ip?: string | null
  public_key?: string | null
  created_at: string
  last_config_issued_at?: string | null
  last_handshake_at?: string | null
  transfer_received_label?: string | null
  transfer_sent_label?: string | null
  revoked_at?: string | null
  failure_message?: string | null
}

export interface DeviceCreateIn {
  name: string
  server_node_id?: string | null
}

export interface IssueResultOut {
  device_id: string
  config: string
  vpn_url?: string | null
  expires_at: string
}

export interface DeviceCreateOut {
  device: DeviceOut
  issue_result: IssueResultOut
}

export interface ServerOut {
  id: string
  name: string
  region_note?: string | null
  status: ServerStatus
}

export interface SupportViewOut {
  visible: boolean
  title?: string | null
  description?: string | null
  sbp_phone?: string | null
  bank_name?: string | null
  extra_contact?: string | null
  monthly_cost_amount?: number | null
  reserve_amount?: number | null
}

export interface SupportHistoryOut {
  visible: boolean
  items: ContributionOut[]
}

export interface AdminUserOut extends UserOut {
  is_active: boolean
  device_limit?: number | null
  device_limit_unlimited: boolean
  show_server_support: boolean
  free_access: boolean
  note?: string | null
  active_device_count?: number
  created_at: string
}

export interface AdminUserCreateIn {
  login: string
  display_name: string
  password: string
  role?: UserRole
  telegram_username?: string | null
  device_limit?: number | null
  device_limit_unlimited?: boolean
  show_server_support?: boolean
  free_access?: boolean
  note?: string | null
}

export interface AdminUserUpdateIn {
  display_name?: string | null
  role?: UserRole | null
  telegram_username?: string | null
  device_limit?: number | null
  device_limit_unlimited?: boolean | null
  show_server_support?: boolean | null
  free_access?: boolean | null
  note?: string | null
}

export interface ResetPasswordIn {
  password: string
}

export interface ContributionCreateIn {
  amount: number
  currency?: string
  period_label?: string | null
  comment?: string | null
}

export interface ContributionOut {
  id: string
  amount: number
  currency: string
  period_label?: string | null
  comment?: string | null
  recorded_at: string
}

export interface AdminServerOut {
  id: string
  name: string
  public_host: string
  public_port?: number | null
  region_note?: string | null
  provider?: string | null
  agent_base_url: string
  agent_key_id?: string | null
  has_agent_secret: boolean
  agent_allowed_ip_note?: string | null
  status: ServerStatus
  last_seen_at?: string | null
  last_error?: string | null
  last_status_payload?: Record<string, unknown> | null
  awg_container_name: string
  awg_interface: string
  awg_config_path: string
  clients_table_path: string
  is_available_for_new_devices: boolean
  active_device_count?: number
  created_at: string
}

export interface AdminServerCreateIn {
  name: string
  public_host: string
  agent_base_url: string
  public_port?: number | null
  region_note?: string | null
  provider?: string | null
  agent_key_id?: string | null
  agent_secret?: string | null
  agent_allowed_ip_note?: string | null
  is_available_for_new_devices?: boolean
}

export interface AdminServerUpdateIn {
  name?: string | null
  public_host?: string | null
  agent_base_url?: string | null
  public_port?: number | null
  region_note?: string | null
  provider?: string | null
  agent_key_id?: string | null
  agent_secret?: string | null
  agent_allowed_ip_note?: string | null
  is_available_for_new_devices?: boolean | null
  awg_container_name?: string | null
  awg_interface?: string | null
  awg_config_path?: string | null
  clients_table_path?: string | null
}

export interface AgentPeerOut {
  public_key: string
  name?: string | null
  allowed_ips_config?: string[] | null
  allowed_ips_runtime?: string[] | null
  in_config?: boolean
  in_runtime?: boolean
  in_clients_table?: boolean
  endpoint?: string | null
  latest_handshake?: string | null
  transfer_received?: string | null
  transfer_sent?: string | null
  user_data?: Record<string, unknown> | null
}

export interface SetupJobCreateIn {
  server_name: string
  host: string
  ssh_port?: number
  ssh_username?: string
  auth_method: AuthMethod
  secret: string
  region_note?: string | null
  install_awg?: boolean
  available_for_new_devices?: boolean
  verify_before_install?: boolean
}

export interface SetupJobOut {
  id: string
  status: SetupJobStatus
  current_step: string
  server_name: string
  host: string
  ssh_port: number
  ssh_username: string
  auth_method: AuthMethod
  region_note?: string | null
  install_awg: boolean
  available_for_new_devices: boolean
  verify_before_install: boolean
  error_message?: string | null
  server_node_id?: string | null
  created_at: string
  started_at?: string | null
  finished_at?: string | null
  agent_base_url?: string | null
  agent_allow_ips: string[]
}

export interface SetupJobEventOut {
  level: EventLevel
  step: string
  message: string
  metadata?: Record<string, unknown>
  created_at: string
}

export interface SupportSettingsOut {
  title: string
  description: string
  sbp_phone?: string | null
  bank_name?: string | null
  extra_contact?: string | null
  monthly_cost_amount?: number | null
  reserve_amount?: number | null
  is_enabled: boolean
  updated_at?: string | null
}

export interface SupportSettingsUpdateIn {
  title?: string | null
  description?: string | null
  sbp_phone?: string | null
  bank_name?: string | null
  extra_contact?: string | null
  monthly_cost_amount?: number | null
  reserve_amount?: number | null
  is_enabled?: boolean | null
}

export interface AuditLogOut {
  id: string
  action: string
  actor_user_id?: string | null
  target_type?: string | null
  target_id?: string | null
  metadata?: Record<string, unknown>
  ip_address?: string | null
  user_agent?: string | null
  created_at: string
}
