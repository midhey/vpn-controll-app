export function formatDate(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

export function formatMoney(amount?: number | null, currency = 'RUB'): string {
  if (amount === undefined || amount === null) return '—'
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(amount)
}

export function formatLimit(used: number, limit?: number | null, unlimited?: boolean): string {
  if (unlimited) return `${used} / без лимита`
  return `${used} / ${limit ?? 0}`
}

export function compactId(value?: string | null): string {
  if (!value) return '—'
  if (value.length <= 12) return value
  return `${value.slice(0, 6)}…${value.slice(-4)}`
}

export function statusLabel(value: string): string {
  const labels: Record<string, string> = {
    provisioning: 'Выпускается',
    active: 'Активно',
    revoked: 'Отозвано',
    failed: 'Ошибка',
    draft: 'Черновик',
    setup_pending: 'Ожидает setup',
    setup_running: 'Setup идёт',
    online: 'Онлайн',
    warning: 'Предупреждение',
    offline: 'Офлайн',
    disabled: 'Отключён',
    setup_failed: 'Setup упал',
    queued: 'В очереди',
    checking_ssh: 'Проверка SSH',
    installing_agent: 'Агент',
    installing_vpn: 'VPN',
    verifying: 'Проверка',
    success: 'Готово',
    cancelled: 'Отменено',
    info: 'Инфо',
    error: 'Ошибка',
  }
  return labels[value] || value
}

export function statusTone(value: string): 'neutral' | 'good' | 'warn' | 'danger' {
  if (['active', 'online', 'success', 'info'].includes(value)) return 'good'
  if (['warning', 'provisioning', 'queued', 'checking_ssh', 'installing_agent', 'installing_vpn', 'verifying'].includes(value)) return 'warn'
  if (['revoked', 'failed', 'offline', 'disabled', 'setup_failed', 'cancelled', 'error'].includes(value)) return 'danger'
  return 'neutral'
}
