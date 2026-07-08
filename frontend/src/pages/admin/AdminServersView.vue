<script setup lang="ts">
import { Plus, RotateCw, Stethoscope } from '@lucide/vue'
import { onMounted, ref } from 'vue'
import { adminApi } from '@/domains/admin/api'
import { errorMessage } from '@/shared/api/client'
import type { AdminServerOut } from '@/shared/api/types'
import { formatDate } from '@/shared/lib/format'
import EmptyState from '@/shared/ui/EmptyState.vue'
import ErrorBanner from '@/shared/ui/ErrorBanner.vue'
import LoadingState from '@/shared/ui/LoadingState.vue'
import StatusBadge from '@/shared/ui/StatusBadge.vue'

const servers = ref<AdminServerOut[]>([])
const loading = ref(true)
const pendingId = ref('')
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    servers.value = await adminApi.servers.list()
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    loading.value = false
  }
}

async function healthCheck(serverId: string) {
  pendingId.value = serverId
  error.value = ''
  try {
    const updated = await adminApi.servers.healthCheck(serverId)
    servers.value = servers.value.map((server) => (server.id === updated.id ? updated : server))
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    pendingId.value = ''
  }
}

async function toggle(server: AdminServerOut) {
  pendingId.value = server.id
  error.value = ''
  try {
    const updated =
      server.status === 'disabled'
        ? await adminApi.servers.enable(server.id)
        : await adminApi.servers.disable(server.id)
    servers.value = servers.value.map((item) => (item.id === updated.id ? updated : item))
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    pendingId.value = ''
  }
}

onMounted(load)
</script>

<template>
  <section class="page is-wide">
    <header class="page-header">
      <div>
        <h1>Servers</h1>
        <p>Ручные серверы, health-check, enable/disable и peers.</p>
      </div>
      <div class="page-actions">
        <button class="ghost-button" type="button" @click="load"><RotateCw :size="16" /> Обновить</button>
        <RouterLink class="button" to="/admin/servers/new"><Plus :size="17" /> Создать</RouterLink>
      </div>
    </header>

    <ErrorBanner v-if="error" :message="error" />
    <section class="panel">
      <LoadingState v-if="loading" />
      <EmptyState v-else-if="servers.length === 0" title="Серверов нет" />
      <div v-else class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Node</th>
              <th>Endpoint</th>
              <th>Status</th>
              <th>Devices</th>
              <th>Last seen</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="server in servers" :key="server.id">
              <td>
                <strong>{{ server.name }}</strong>
                <div class="muted">{{ server.provider || 'manual' }} · {{ server.region_note || 'no region' }}</div>
              </td>
              <td>
                <div>{{ server.public_host }}{{ server.public_port ? `:${server.public_port}` : '' }}</div>
                <div class="muted mono">{{ server.agent_base_url }}</div>
              </td>
              <td><StatusBadge :status="server.status" /></td>
              <td>{{ server.active_device_count ?? 0 }} · {{ server.is_available_for_new_devices ? 'available' : 'blocked' }}</td>
              <td>{{ formatDate(server.last_seen_at) }}</td>
              <td>
                <div class="row-actions">
                  <button class="ghost-button" type="button" :disabled="pendingId === server.id" @click="healthCheck(server.id)">
                    <Stethoscope :size="16" /> Health
                  </button>
                  <button class="ghost-button" type="button" :disabled="pendingId === server.id" @click="toggle(server)">
                    {{ server.status === 'disabled' ? 'Enable' : 'Disable' }}
                  </button>
                  <RouterLink class="ghost-button" :to="`/admin/servers/${server.id}`">Открыть</RouterLink>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </section>
</template>
