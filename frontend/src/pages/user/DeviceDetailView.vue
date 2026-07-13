<script setup lang="ts">
import { Download, RotateCw, Trash2 } from '@lucide/vue'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as devicesApi from '@/domains/devices/api'
import { errorMessage, isApiError } from '@/shared/api/client'
import type { DeviceOut, IssueResultOut } from '@/shared/api/types'
import { formatDate } from '@/shared/lib/format'
import CopyField from '@/shared/ui/CopyField.vue'
import ErrorBanner from '@/shared/ui/ErrorBanner.vue'
import LoadingState from '@/shared/ui/LoadingState.vue'
import StatusBadge from '@/shared/ui/StatusBadge.vue'

const props = defineProps<{ id: string }>()
const router = useRouter()

const device = ref<DeviceOut | null>(null)
const issue = ref<IssueResultOut | null>(null)
const loading = ref(true)
const pending = ref(false)
const error = ref('')
const issueMessage = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    device.value = await devicesApi.getDevice(props.id)
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    loading.value = false
  }
}

async function fetchIssueResult() {
  pending.value = true
  issueMessage.value = ''
  try {
    issue.value = await devicesApi.getIssueResult(props.id)
  } catch (err) {
    issue.value = null
    issueMessage.value = isApiError(err) && err.status === 404 ? 'Свежий результат выпуска уже недоступен.' : errorMessage(err)
  } finally {
    pending.value = false
  }
}

async function revoke() {
  if (!window.confirm('Отозвать это устройство?')) return
  pending.value = true
  error.value = ''
  try {
    device.value = await devicesApi.revokeDevice(props.id)
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    pending.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <h1>{{ device?.name || 'Устройство' }}</h1>
        <p>Детали peer, трафик и отзыв доступа.</p>
      </div>
      <div class="page-actions">
        <button class="ghost-button" type="button" @click="router.back()">Назад</button>
        <button class="ghost-button" type="button" @click="load"><RotateCw :size="16" /> Обновить</button>
      </div>
    </header>

    <LoadingState v-if="loading" />
    <ErrorBanner v-else-if="error" :message="error" />

    <template v-else-if="device">
      <section class="panel">
        <div class="panel-header">
          <div>
            <h2>{{ device.name }}</h2>
            <p class="mono">{{ device.id }}</p>
          </div>
          <StatusBadge :status="device.status" />
        </div>
        <div class="panel-body detail-grid">
          <div><span>Сервер</span><strong>{{ device.server_name || device.server_node_id }}</strong></div>
          <div><span>Client IP</span><strong class="mono">{{ device.client_ip || '—' }}</strong></div>
          <div><span>Public key</span><strong class="mono">{{ device.public_key || '—' }}</strong></div>
          <div><span>Создано</span><strong>{{ formatDate(device.created_at) }}</strong></div>
          <div><span>Config issued</span><strong>{{ formatDate(device.last_config_issued_at) }}</strong></div>
          <div><span>Handshake</span><strong>{{ formatDate(device.last_handshake_at) }}</strong></div>
          <div><span>RX</span><strong>{{ device.transfer_received_label || '—' }}</strong></div>
          <div><span>TX</span><strong>{{ device.transfer_sent_label || '—' }}</strong></div>
          <div v-if="device.failure_message"><span>Ошибка</span><strong>{{ device.failure_message }}</strong></div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <div>
            <h2>Config / VPN URL</h2>
            <p>Backend отдаёт свежий результат только пока он не истёк.</p>
          </div>
          <button class="ghost-button" type="button" :disabled="pending" @click="fetchIssueResult">
            <Download :size="16" /> Получить
          </button>
        </div>
        <div class="panel-body form-grid">
          <p v-if="issueMessage" class="muted">{{ issueMessage }}</p>
          <template v-if="issue">
            <CopyField label="Config" :value="issue.config" multiline />
            <CopyField v-if="issue.vpn_url" label="VPN URL" :value="issue.vpn_url" />
          </template>
        </div>
      </section>

      <section class="panel danger-zone">
        <div class="panel-header">
          <div>
            <h2>Отзыв устройства</h2>
            <p>Повторный отзыв идемпотентен на backend.</p>
          </div>
          <button class="danger-button" type="button" :disabled="pending" @click="revoke">
            <Trash2 :size="16" /> Отозвать
          </button>
        </div>
      </section>
    </template>
  </section>
</template>

<style scoped lang="scss">
.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;

  div {
    display: grid;
    gap: 5px;
    min-width: 0;
    padding: 10px;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-small);
    background: var(--color-surface-inset);
  }

  span {
    color: var(--color-text-muted);
    font-size: 11px;
    font-weight: 800;
    text-transform: uppercase;
  }

  strong {
    min-width: 0;
    overflow-wrap: anywhere;
    color: var(--color-text-strong);
    font-size: 13px;
  }
}

@media (max-width: 760px) {
  .detail-grid {
    grid-template-columns: 1fr;
  }
}
</style>
