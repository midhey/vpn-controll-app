<script setup lang="ts">
import { RotateCw } from '@lucide/vue'
import { onMounted, ref } from 'vue'
import * as serversApi from '@/domains/servers/api'
import { errorMessage } from '@/shared/api/client'
import type { ServerOut } from '@/shared/api/types'
import EmptyState from '@/shared/ui/EmptyState.vue'
import ErrorBanner from '@/shared/ui/ErrorBanner.vue'
import LoadingState from '@/shared/ui/LoadingState.vue'
import StatusBadge from '@/shared/ui/StatusBadge.vue'

const servers = ref<ServerOut[]>([])
const loading = ref(true)
const error = ref('')

async function load() {
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

onMounted(load)
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <h1>Серверы</h1>
        <p>Только доступные пользователю серверы без технических хостов, URL агента и секретов.</p>
      </div>
      <div class="page-actions">
        <button class="ghost-button" type="button" @click="load"><RotateCw :size="16" /> Обновить</button>
      </div>
    </header>

    <section class="panel">
      <LoadingState v-if="loading" />
      <ErrorBanner v-else-if="error" :message="error" />
      <EmptyState v-else-if="servers.length === 0" title="Нет доступных серверов" text="Администратор ещё не включил серверы для новых устройств." />
      <div v-else class="table-wrap">
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
  </section>
</template>
