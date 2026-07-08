<script setup lang="ts">
import { Check, Plus, Server } from '@lucide/vue'
import { onMounted, reactive, ref } from 'vue'
import * as devicesApi from '@/domains/devices/api'
import * as serversApi from '@/domains/servers/api'
import { errorMessage } from '@/shared/api/client'
import type { DeviceCreateOut, ServerOut } from '@/shared/api/types'
import { formatDate } from '@/shared/lib/format'
import CopyField from '@/shared/ui/CopyField.vue'
import EmptyState from '@/shared/ui/EmptyState.vue'
import ErrorBanner from '@/shared/ui/ErrorBanner.vue'
import LoadingState from '@/shared/ui/LoadingState.vue'
import StatusBadge from '@/shared/ui/StatusBadge.vue'

const servers = ref<ServerOut[]>([])
const result = ref<DeviceCreateOut | null>(null)
const loading = ref(true)
const pending = ref(false)
const error = ref('')
const form = reactive({
  name: '',
  server_node_id: '',
})

async function loadServers() {
  loading.value = true
  error.value = ''
  try {
    servers.value = await serversApi.listServers()
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    loading.value = false
  }
}

async function submit() {
  pending.value = true
  error.value = ''
  result.value = null
  try {
    result.value = await devicesApi.createDevice({
      name: form.name,
      server_node_id: form.server_node_id || null,
    })
    form.name = ''
    form.server_node_id = ''
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    pending.value = false
  }
}

onMounted(loadServers)
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <h1>Выпуск устройства</h1>
        <p>Выберите сервер вручную или оставьте авто-выбор. Результат выдаётся один раз и доступен ограниченное время.</p>
      </div>
    </header>

    <LoadingState v-if="loading" />
    <ErrorBanner v-else-if="error" :message="error" />

    <template v-else>
      <section class="panel">
        <div class="panel-header">
          <div>
            <h2>Параметры</h2>
            <p>Имя будет видно в списке устройств и peer-таблицах.</p>
          </div>
        </div>
        <form class="panel-body form-grid" @submit.prevent="submit">
          <label class="field">
            <span>Имя устройства</span>
            <input v-model.trim="form.name" maxlength="64" required placeholder="Например, iPhone 15" />
          </label>
          <label class="field">
            <span>Сервер</span>
            <select v-model="form.server_node_id">
              <option value="">Авто-выбор backend</option>
              <option v-for="server in servers" :key="server.id" :value="server.id">
                {{ server.name }}{{ server.region_note ? ` · ${server.region_note}` : '' }}
              </option>
            </select>
          </label>
          <button class="button" type="submit" :disabled="pending || !form.name">
            <Plus :size="17" />
            {{ pending ? 'Выпускаю…' : 'Выпустить config' }}
          </button>
        </form>
      </section>

      <EmptyState
        v-if="servers.length === 0"
        title="Нет доступных серверов"
        text="Backend не вернул серверы для новых устройств. Администратор должен включить доступный node."
      />

      <section v-if="result" class="panel">
        <div class="panel-header">
          <div>
            <h2><Check :size="17" /> Config выпущен</h2>
            <p>Истекает: {{ formatDate(result.issue_result.expires_at) }}</p>
          </div>
          <RouterLink class="ghost-button" :to="`/devices/${result.device.id}`">Открыть устройство</RouterLink>
        </div>
        <div class="panel-body form-grid">
          <div class="device-result">
            <div>
              <strong>{{ result.device.name }}</strong>
              <p>{{ result.device.server_name || result.device.server_node_id }}</p>
            </div>
            <StatusBadge :status="result.device.status" />
          </div>
          <CopyField label="Config" :value="result.issue_result.config" multiline />
          <CopyField v-if="result.issue_result.vpn_url" label="VPN URL" :value="result.issue_result.vpn_url" />
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <div>
            <h2><Server :size="17" /> Серверы для выпуска</h2>
            <p>В обычном режиме пользователю не показываются хосты и секреты агента.</p>
          </div>
        </div>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Имя</th>
                <th>Регион</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="server in servers" :key="server.id">
                <td>{{ server.name }}</td>
                <td>{{ server.region_note || '—' }}</td>
                <td><StatusBadge :status="server.status" /></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </section>
</template>

<style scoped lang="scss">
.device-result {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: rgba(30, 44, 70, 0.45);

  strong {
    color: var(--text-strong);
  }

  p {
    margin: 4px 0 0;
    color: var(--muted);
  }
}
</style>
