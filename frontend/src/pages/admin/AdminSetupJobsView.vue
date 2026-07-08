<script setup lang="ts">
import { Play, Plus, RotateCw, XCircle } from '@lucide/vue'
import { onMounted, ref } from 'vue'
import { adminApi } from '@/domains/admin/api'
import { errorMessage } from '@/shared/api/client'
import type { SetupJobOut } from '@/shared/api/types'
import { formatDate } from '@/shared/lib/format'
import EmptyState from '@/shared/ui/EmptyState.vue'
import ErrorBanner from '@/shared/ui/ErrorBanner.vue'
import LoadingState from '@/shared/ui/LoadingState.vue'
import StatusBadge from '@/shared/ui/StatusBadge.vue'

const jobs = ref<SetupJobOut[]>([])
const loading = ref(true)
const pendingId = ref('')
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    jobs.value = await adminApi.setupJobs.list()
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    loading.value = false
  }
}

async function start(jobId: string) {
  pendingId.value = jobId
  error.value = ''
  try {
    const updated = await adminApi.setupJobs.start(jobId)
    jobs.value = jobs.value.map((job) => (job.id === updated.id ? updated : job))
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    pendingId.value = ''
  }
}

async function cancel(jobId: string) {
  pendingId.value = jobId
  error.value = ''
  try {
    const updated = await adminApi.setupJobs.cancel(jobId)
    jobs.value = jobs.value.map((job) => (job.id === updated.id ? updated : job))
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
        <h1>Setup jobs</h1>
        <p>Создание сервера через SSH setup flow, запуск, отмена и просмотр событий.</p>
      </div>
      <div class="page-actions">
        <button class="ghost-button" type="button" @click="load"><RotateCw :size="16" /> Обновить</button>
        <RouterLink class="button" to="/admin/setup-jobs/new"><Plus :size="17" /> Создать</RouterLink>
      </div>
    </header>

    <ErrorBanner v-if="error" :message="error" />
    <section class="panel">
      <LoadingState v-if="loading" />
      <EmptyState v-else-if="jobs.length === 0" title="Setup jobs нет" />
      <div v-else class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Job</th>
              <th>Status</th>
              <th>Host</th>
              <th>Step</th>
              <th>Created</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="job in jobs" :key="job.id">
              <td>
                <strong>{{ job.server_name }}</strong>
                <div class="muted mono">{{ job.id }}</div>
              </td>
              <td><StatusBadge :status="job.status" /></td>
              <td>{{ job.host }}:{{ job.ssh_port }}</td>
              <td>{{ job.current_step }}</td>
              <td>{{ formatDate(job.created_at) }}</td>
              <td>
                <div class="row-actions">
                  <button class="ghost-button" type="button" :disabled="pendingId === job.id" @click="start(job.id)">
                    <Play :size="16" /> Start
                  </button>
                  <button class="ghost-button" type="button" :disabled="pendingId === job.id" @click="cancel(job.id)">
                    <XCircle :size="16" /> Cancel
                  </button>
                  <RouterLink class="ghost-button" :to="`/admin/setup-jobs/${job.id}`">Открыть</RouterLink>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </section>
</template>
