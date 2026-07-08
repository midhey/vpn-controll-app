<script setup lang="ts">
import { Power, RotateCw, Save, Stethoscope } from '@lucide/vue'
import { onMounted, reactive, ref } from 'vue'
import { adminApi } from '@/domains/admin/api'
import { errorMessage } from '@/shared/api/client'
import type { AdminServerOut, AgentPeerOut } from '@/shared/api/types'
import { compactId, formatDate } from '@/shared/lib/format'
import EmptyState from '@/shared/ui/EmptyState.vue'
import ErrorBanner from '@/shared/ui/ErrorBanner.vue'
import LoadingState from '@/shared/ui/LoadingState.vue'
import StatusBadge from '@/shared/ui/StatusBadge.vue'

const props = defineProps<{ id: string }>()

const server = ref<AdminServerOut | null>(null)
const peers = ref<AgentPeerOut[]>([])
const loading = ref(true)
const peersLoading = ref(false)
const pending = ref(false)
const error = ref('')
const notice = ref('')
const form = reactive({
  name: '',
  public_host: '',
  public_port: 0,
  agent_base_url: '',
  region_note: '',
  provider: '',
  agent_key_id: '',
  agent_secret: '',
  agent_allowed_ip_note: '',
  is_available_for_new_devices: true,
  awg_container_name: '',
  awg_interface: '',
  awg_config_path: '',
  clients_table_path: '',
})

function assignForm(value: AdminServerOut) {
  Object.assign(form, {
    name: value.name,
    public_host: value.public_host,
    public_port: value.public_port ?? 0,
    agent_base_url: value.agent_base_url,
    region_note: value.region_note || '',
    provider: value.provider || '',
    agent_key_id: value.agent_key_id || '',
    agent_secret: '',
    agent_allowed_ip_note: value.agent_allowed_ip_note || '',
    is_available_for_new_devices: value.is_available_for_new_devices,
    awg_container_name: value.awg_container_name,
    awg_interface: value.awg_interface,
    awg_config_path: value.awg_config_path,
    clients_table_path: value.clients_table_path,
  })
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    server.value = await adminApi.servers.get(props.id)
    assignForm(server.value)
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    loading.value = false
  }
}

async function save() {
  pending.value = true
  error.value = ''
  notice.value = ''
  try {
    server.value = await adminApi.servers.update(props.id, {
      name: form.name,
      public_host: form.public_host,
      public_port: form.public_port || null,
      agent_base_url: form.agent_base_url,
      region_note: form.region_note || null,
      provider: form.provider || null,
      agent_key_id: form.agent_key_id || null,
      agent_secret: form.agent_secret || null,
      agent_allowed_ip_note: form.agent_allowed_ip_note || null,
      is_available_for_new_devices: form.is_available_for_new_devices,
      awg_container_name: form.awg_container_name,
      awg_interface: form.awg_interface,
      awg_config_path: form.awg_config_path,
      clients_table_path: form.clients_table_path,
    })
    assignForm(server.value)
    notice.value = 'Сервер сохранён'
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    pending.value = false
  }
}

async function healthCheck() {
  pending.value = true
  error.value = ''
  try {
    server.value = await adminApi.servers.healthCheck(props.id)
    assignForm(server.value)
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    pending.value = false
  }
}

async function toggle() {
  if (!server.value) return
  pending.value = true
  error.value = ''
  try {
    server.value =
      server.value.status === 'disabled'
        ? await adminApi.servers.enable(props.id)
        : await adminApi.servers.disable(props.id)
    assignForm(server.value)
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    pending.value = false
  }
}

async function loadPeers() {
  peersLoading.value = true
  error.value = ''
  try {
    peers.value = await adminApi.servers.peers(props.id)
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    peersLoading.value = false
  }
}

onMounted(async () => {
  await load()
  await loadPeers()
})
</script>

<template>
  <section class="page is-wide">
    <header class="page-header">
      <div>
        <h1>{{ server?.name || 'Server' }}</h1>
        <p v-if="server">{{ server.public_host }} · {{ server.region_note || 'no region' }}</p>
      </div>
      <div class="page-actions">
        <button class="ghost-button" type="button" @click="load"><RotateCw :size="16" /> Обновить</button>
        <button class="ghost-button" type="button" :disabled="pending" @click="healthCheck"><Stethoscope :size="16" /> Health</button>
        <button v-if="server" class="danger-button" type="button" :disabled="pending" @click="toggle">
          <Power :size="16" /> {{ server.status === 'disabled' ? 'Enable' : 'Disable' }}
        </button>
      </div>
    </header>

    <LoadingState v-if="loading" />
    <ErrorBanner v-else-if="error" :message="error" />
    <div v-if="notice" class="alert">{{ notice }}</div>

    <template v-if="!loading && server">
      <div class="grid cols-2">
        <section class="panel">
          <div class="panel-header">
            <div>
              <h2>Параметры</h2>
              <p>Agent secret можно заменить, но текущее значение не показывается.</p>
            </div>
            <StatusBadge :status="server.status" />
          </div>
          <form class="panel-body form-grid cols-2" @submit.prevent="save">
            <label class="field"><span>Name</span><input v-model.trim="form.name" required /></label>
            <label class="field"><span>Public host</span><input v-model.trim="form.public_host" required /></label>
            <label class="field"><span>Public port</span><input v-model.number="form.public_port" type="number" min="0" max="65535" /></label>
            <label class="field"><span>Agent URL</span><input v-model.trim="form.agent_base_url" required /></label>
            <label class="field"><span>Region</span><input v-model.trim="form.region_note" /></label>
            <label class="field"><span>Provider</span><input v-model.trim="form.provider" /></label>
            <label class="field"><span>Agent key id</span><input v-model.trim="form.agent_key_id" /></label>
            <label class="field"><span>New agent secret</span><input v-model="form.agent_secret" type="password" autocomplete="new-password" /></label>
            <label class="field"><span>Allowed IP note</span><input v-model.trim="form.agent_allowed_ip_note" /></label>
            <label class="check-field"><input v-model="form.is_available_for_new_devices" type="checkbox" /> Доступен для новых устройств</label>
            <label class="field"><span>AWG container</span><input v-model.trim="form.awg_container_name" /></label>
            <label class="field"><span>AWG interface</span><input v-model.trim="form.awg_interface" /></label>
            <label class="field"><span>AWG config path</span><input v-model.trim="form.awg_config_path" /></label>
            <label class="field"><span>Clients table path</span><input v-model.trim="form.clients_table_path" /></label>
            <div class="page-actions">
              <button class="button" type="submit" :disabled="pending"><Save :size="16" /> Сохранить</button>
            </div>
          </form>
        </section>

        <section class="panel">
          <div class="panel-header">
            <div>
              <h2>Состояние</h2>
              <p>Последний health-check и runtime markers.</p>
            </div>
          </div>
          <div class="panel-body detail-list">
            <div><span>Last seen</span><strong>{{ formatDate(server.last_seen_at) }}</strong></div>
            <div><span>Last error</span><strong>{{ server.last_error || '—' }}</strong></div>
            <div><span>Agent secret</span><strong>{{ server.has_agent_secret ? 'задан' : 'не задан' }}</strong></div>
            <div><span>Active devices</span><strong>{{ server.active_device_count ?? 0 }}</strong></div>
            <div><span>Created</span><strong>{{ formatDate(server.created_at) }}</strong></div>
          </div>
        </section>
      </div>

      <section class="panel">
        <div class="panel-header">
          <div>
            <h2>Peers</h2>
            <p>Сводка из agent runtime/config/clients table.</p>
          </div>
          <button class="ghost-button" type="button" @click="loadPeers"><RotateCw :size="16" /> Обновить peers</button>
        </div>
        <LoadingState v-if="peersLoading" />
        <EmptyState v-else-if="peers.length === 0" title="Peers не найдены" />
        <div v-else class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Peer</th>
                <th>Allowed IPs</th>
                <th>Runtime</th>
                <th>Handshake</th>
                <th>Transfer</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="peer in peers" :key="peer.public_key">
                <td>
                  <strong>{{ peer.name || 'без имени' }}</strong>
                  <div class="muted mono">{{ compactId(peer.public_key) }}</div>
                </td>
                <td>{{ (peer.allowed_ips_runtime || peer.allowed_ips_config || []).join(', ') || '—' }}</td>
                <td>
                  cfg {{ peer.in_config ? 'yes' : 'no' }} · run {{ peer.in_runtime ? 'yes' : 'no' }} · table
                  {{ peer.in_clients_table ? 'yes' : 'no' }}
                </td>
                <td>{{ peer.latest_handshake || '—' }}</td>
                <td>{{ peer.transfer_received || '0' }} / {{ peer.transfer_sent || '0' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </section>
</template>

<style scoped lang="scss">
.detail-list {
  display: grid;
  gap: 10px;

  div {
    display: grid;
    gap: 4px;
    padding: 10px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: rgba(10, 16, 32, 0.52);
  }

  span {
    color: var(--muted);
    font-size: 11px;
    font-weight: 800;
    text-transform: uppercase;
  }

  strong {
    overflow-wrap: anywhere;
    color: var(--text-strong);
  }
}
</style>
