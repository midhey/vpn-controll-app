<script setup lang="ts">
import { Plus, RotateCw } from '@lucide/vue'
import { onMounted, ref } from 'vue'
import * as devicesApi from '@/domains/devices/api'
import type { DeviceOut } from '@/shared/api/types'
import { errorMessage } from '@/shared/api/client'
import { formatDate } from '@/shared/lib/format'
import EmptyState from '@/shared/ui/EmptyState.vue'
import ErrorBanner from '@/shared/ui/ErrorBanner.vue'
import LoadingState from '@/shared/ui/LoadingState.vue'
import StatusBadge from '@/shared/ui/StatusBadge.vue'

const devices = ref<DeviceOut[]>([])
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    devices.value = await devicesApi.listDevices()
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="page is-wide">
    <header class="page-header">
      <div>
        <h1>Устройства</h1>
        <p>Активные и отозванные VPN-конфиги текущего пользователя.</p>
      </div>
      <div class="page-actions">
        <button class="ghost-button" type="button" @click="load"><RotateCw :size="16" /> Обновить</button>
        <RouterLink class="button" to="/devices/new"><Plus :size="17" /> Выпустить</RouterLink>
      </div>
    </header>

    <section class="panel">
      <LoadingState v-if="loading" />
      <ErrorBanner v-else-if="error" :message="error" />
      <EmptyState
        v-else-if="devices.length === 0"
        title="Нет устройств"
        text="Создайте устройство, выберите сервер и сразу скопируйте выданный config или VPN URL."
      >
        <RouterLink class="button" to="/devices/new"><Plus :size="17" /> Создать</RouterLink>
      </EmptyState>
      <div v-else class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Устройство</th>
              <th>Статус</th>
              <th>Сервер</th>
              <th>IP</th>
              <th>Handshake</th>
              <th>Создано</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="device in devices" :key="device.id">
              <td>
                <strong>{{ device.name }}</strong>
                <div class="muted mono">{{ device.id }}</div>
              </td>
              <td><StatusBadge :status="device.status" /></td>
              <td>{{ device.server_name || device.server_node_id }}</td>
              <td class="mono">{{ device.client_ip || '—' }}</td>
              <td>{{ formatDate(device.last_handshake_at) }}</td>
              <td>{{ formatDate(device.created_at) }}</td>
              <td><RouterLink class="ghost-button" :to="`/devices/${device.id}`">Открыть</RouterLink></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </section>
</template>
