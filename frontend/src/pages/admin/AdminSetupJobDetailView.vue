<script setup lang="ts">
import { Play, RotateCw, XCircle } from '@lucide/vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { adminApi } from '@/domains/admin/api'
import { errorMessage } from '@/shared/api/client'
import type { SetupJobEventOut, SetupJobOut } from '@/shared/api/types'
import { formatDate } from '@/shared/lib/format'
import EmptyState from '@/shared/ui/EmptyState.vue'
import ErrorBanner from '@/shared/ui/ErrorBanner.vue'
import LoadingState from '@/shared/ui/LoadingState.vue'
import StatusBadge from '@/shared/ui/StatusBadge.vue'

const props = defineProps<{ id: string }>()

const job = ref<SetupJobOut | null>(null)
const events = ref<SetupJobEventOut[]>([])
const loading = ref(true)
const pending = ref(false)
const error = ref('')
let timer: number | undefined

const isTerminal = computed(() =>
  job.value ? ['success', 'failed', 'cancelled'].includes(job.value.status) : false,
)

async function load() {
  error.value = ''
  try {
    const [jobResult, eventsResult] = await Promise.all([
      adminApi.setupJobs.get(props.id),
      adminApi.setupJobs.events(props.id),
    ])
    job.value = jobResult
    events.value = eventsResult
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    loading.value = false
  }
}

async function start() {
  pending.value = true
  try {
    job.value = await adminApi.setupJobs.start(props.id)
    await load()
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    pending.value = false
  }
}

async function cancel() {
  pending.value = true
  try {
    job.value = await adminApi.setupJobs.cancel(props.id)
    await load()
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    pending.value = false
  }
}

onMounted(async () => {
  await load()
  timer = window.setInterval(() => {
    if (!isTerminal.value) void load()
  }, 3000)
})

onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<template>
  <section class="page is-wide">
    <header class="page-header">
      <div>
        <h1>{{ job?.server_name || 'Setup job' }}</h1>
        <p v-if="job">{{ job.host }}:{{ job.ssh_port }} · {{ job.current_step }}</p>
      </div>
      <div class="page-actions">
        <button class="ghost-button" type="button" @click="load"><RotateCw :size="16" /> Обновить</button>
        <button class="ghost-button" type="button" :disabled="pending" @click="start"><Play :size="16" /> Start</button>
        <button class="danger-button" type="button" :disabled="pending" @click="cancel"><XCircle :size="16" /> Cancel</button>
      </div>
    </header>

    <LoadingState v-if="loading" />
    <ErrorBanner v-else-if="error" :message="error" />

    <template v-if="!loading && job">
      <section class="panel">
        <div class="panel-header">
          <div>
            <h2>Состояние</h2>
            <p class="mono">{{ job.id }}</p>
          </div>
          <StatusBadge :status="job.status" />
        </div>
        <div class="panel-body job-grid">
          <div><span>Step</span><strong>{{ job.current_step }}</strong></div>
          <div><span>Auth</span><strong>{{ job.auth_method }}</strong></div>
          <div><span>Created</span><strong>{{ formatDate(job.created_at) }}</strong></div>
          <div><span>Started</span><strong>{{ formatDate(job.started_at) }}</strong></div>
          <div><span>Finished</span><strong>{{ formatDate(job.finished_at) }}</strong></div>
          <div><span>Server node</span><strong class="mono">{{ job.server_node_id || '—' }}</strong></div>
          <div v-if="job.error_message"><span>Error</span><strong>{{ job.error_message }}</strong></div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <div>
            <h2>Events polling</h2>
            <p>Обновляется каждые 3 секунды до terminal status.</p>
          </div>
        </div>
        <EmptyState v-if="events.length === 0" title="Событий пока нет" />
        <div v-else class="events-list">
          <article v-for="event in events" :key="`${event.created_at}-${event.step}-${event.message}`" class="event-row">
            <StatusBadge :status="event.level" />
            <div>
              <strong>{{ event.step }}</strong>
              <p>{{ event.message }}</p>
              <small>{{ formatDate(event.created_at) }}</small>
            </div>
          </article>
        </div>
      </section>
    </template>
  </section>
</template>

<style scoped lang="scss">
.job-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;

  div {
    display: grid;
    gap: 5px;
    min-width: 0;
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

.events-list {
  display: grid;
  gap: 8px;
  padding: 14px;
}

.event-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: rgba(10, 16, 32, 0.5);

  strong {
    color: var(--text-strong);
  }

  p {
    margin: 4px 0;
    color: var(--text);
  }

  small {
    color: var(--muted);
  }
}

@media (max-width: 760px) {
  .job-grid {
    grid-template-columns: 1fr;
  }
}
</style>
