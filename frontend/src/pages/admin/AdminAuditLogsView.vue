<script setup lang="ts">
import { RotateCw } from '@lucide/vue'
import { onMounted, ref } from 'vue'
import { adminApi } from '@/domains/admin/api'
import { errorMessage } from '@/shared/api/client'
import type { AuditLogOut } from '@/shared/api/types'
import { compactId, formatDate } from '@/shared/lib/format'
import EmptyState from '@/shared/ui/EmptyState.vue'
import ErrorBanner from '@/shared/ui/ErrorBanner.vue'
import LoadingState from '@/shared/ui/LoadingState.vue'

const logs = ref<AuditLogOut[]>([])
const limit = ref(100)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    logs.value = await adminApi.audit.list(limit.value)
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
        <h1>Audit logs</h1>
        <p>События backend без раскрытия секретов и сырых payload-дампов.</p>
      </div>
      <div class="page-actions">
        <label class="field audit-limit">
          <span>Limit</span>
          <select v-model.number="limit" @change="load">
            <option :value="50">50</option>
            <option :value="100">100</option>
            <option :value="250">250</option>
            <option :value="500">500</option>
          </select>
        </label>
        <button class="ghost-button" type="button" @click="load"><RotateCw :size="16" /> Обновить</button>
      </div>
    </header>

    <section class="panel">
      <LoadingState v-if="loading" />
      <ErrorBanner v-else-if="error" :message="error" />
      <EmptyState v-else-if="logs.length === 0" title="Аудит пуст" />
      <div v-else class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Время</th>
              <th>Action</th>
              <th>Actor</th>
              <th>Target</th>
              <th>Client</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="entry in logs" :key="entry.id">
              <td>{{ formatDate(entry.created_at) }}</td>
              <td>{{ entry.action }}</td>
              <td class="mono">{{ compactId(entry.actor_user_id || 'system') }}</td>
              <td>{{ entry.target_type || '—' }} <span class="muted mono">{{ compactId(entry.target_id) }}</span></td>
              <td>
                <div>{{ entry.ip_address || '—' }}</div>
                <div class="muted">{{ entry.user_agent || '' }}</div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </section>
</template>

<style scoped lang="scss">
.audit-limit {
  min-width: 110px;
}
</style>
