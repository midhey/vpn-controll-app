<script setup lang="ts">
import { HardDrive, Plus, Server, Wallet } from '@lucide/vue'
import { onMounted, ref } from 'vue'
import { apiFetch, errorMessage } from '@/shared/api/client'
import type { DashboardOut } from '@/shared/api/types'
import { formatDate, formatLimit } from '@/shared/lib/format'
import EmptyState from '@/shared/ui/EmptyState.vue'
import ErrorBanner from '@/shared/ui/ErrorBanner.vue'
import LoadingState from '@/shared/ui/LoadingState.vue'
import StatusBadge from '@/shared/ui/StatusBadge.vue'

const dashboard = ref<DashboardOut | null>(null)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    dashboard.value = await apiFetch<DashboardOut>('/me/dashboard')
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <h1>Панель</h1>
        <p>Состояние доступа, лимиты устройств и последние выпуски конфигураций.</p>
      </div>
      <div class="page-actions">
        <RouterLink class="button" to="/devices/new"><Plus :size="17" /> Выпустить устройство</RouterLink>
      </div>
    </header>

    <LoadingState v-if="loading" />
    <ErrorBanner v-else-if="error" :message="error" />

    <template v-else-if="dashboard">
      <div class="grid cols-3">
        <article class="panel metric">
          <span>Доступ</span>
          <strong>{{ dashboard.access.is_active ? 'Активен' : 'Недоступен' }}</strong>
          <small>{{ dashboard.access.message }}</small>
        </article>
        <article class="panel metric">
          <span>Устройства</span>
          <strong>{{ formatLimit(dashboard.device_limit.used, dashboard.device_limit.limit, dashboard.device_limit.unlimited) }}</strong>
          <small>учитываются активные и выпускаемые</small>
        </article>
        <article class="panel metric">
          <span>Поддержка</span>
          <strong>{{ dashboard.support.visible ? 'Видна' : 'Скрыта' }}</strong>
          <small>{{ dashboard.support.hint || 'История доступна по правам пользователя' }}</small>
        </article>
      </div>

      <section class="panel">
        <div class="panel-header">
          <div>
            <h2>Последние устройства</h2>
            <p>Быстрый контроль свежих конфигураций.</p>
          </div>
          <RouterLink class="ghost-button" to="/devices"><HardDrive :size="16" /> Все устройства</RouterLink>
        </div>

        <EmptyState
          v-if="dashboard.recent_devices.length === 0"
          title="Устройств пока нет"
          text="Выпустите первый конфиг и скопируйте VPN URL сразу после создания."
        />
        <div v-else class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Имя</th>
                <th>Статус</th>
                <th>Сервер</th>
                <th>Создано</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="device in dashboard.recent_devices" :key="device.id">
                <td>
                  <strong>{{ device.name }}</strong>
                  <div class="muted mono">{{ device.client_ip || device.id }}</div>
                </td>
                <td><StatusBadge :status="device.status" /></td>
                <td>{{ device.server_name || device.server_node_id }}</td>
                <td>{{ formatDate(device.created_at) }}</td>
                <td><RouterLink class="ghost-button" :to="`/devices/${device.id}`">Открыть</RouterLink></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <div class="grid cols-3">
        <RouterLink class="panel quick-link" to="/servers">
          <Server :size="20" />
          <span>Доступные серверы</span>
        </RouterLink>
        <RouterLink class="panel quick-link" to="/support">
          <Wallet :size="20" />
          <span>Поддержка сервера</span>
        </RouterLink>
        <RouterLink class="panel quick-link" to="/devices/new">
          <Plus :size="20" />
          <span>Новый конфиг</span>
        </RouterLink>
      </div>
    </template>
  </section>
</template>

<style scoped lang="scss">
.quick-link {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px;
  color: var(--color-text-strong);
  font-weight: 800;

  svg {
    color: var(--color-action);
  }
}
</style>
