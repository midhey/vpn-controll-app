<script setup lang="ts">
import { Activity, ScrollText, Server, Users } from '@lucide/vue'
import { onMounted, ref } from 'vue'
import { adminApi } from '@/domains/admin/api'
import { errorMessage } from '@/shared/api/client'
import type { AdminServerOut, AdminUserOut, AuditLogOut, SetupJobOut } from '@/shared/api/types'
import { formatDate } from '@/shared/lib/format'
import ErrorBanner from '@/shared/ui/ErrorBanner.vue'
import LoadingState from '@/shared/ui/LoadingState.vue'
import StatusBadge from '@/shared/ui/StatusBadge.vue'

const users = ref<AdminUserOut[]>([])
const servers = ref<AdminServerOut[]>([])
const jobs = ref<SetupJobOut[]>([])
const audit = ref<AuditLogOut[]>([])
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [usersResult, serversResult, jobsResult, auditResult] = await Promise.all([
      adminApi.users.list(),
      adminApi.servers.list(),
      adminApi.setupJobs.list(),
      adminApi.audit.list(20),
    ])
    users.value = usersResult
    servers.value = serversResult
    jobs.value = jobsResult
    audit.value = auditResult
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
        <h1>Admin</h1>
        <p>Операционная панель для пользователей, серверов, setup jobs и аудита.</p>
      </div>
    </header>

    <LoadingState v-if="loading" />
    <ErrorBanner v-else-if="error" :message="error" />

    <template v-else>
      <div class="grid cols-3">
        <RouterLink class="panel metric nav-metric" to="/admin/users">
          <span><Users :size="16" /> Users</span>
          <strong>{{ users.length }}</strong>
          <small>{{ users.filter((user) => user.is_active).length }} активных</small>
        </RouterLink>
        <RouterLink class="panel metric nav-metric" to="/admin/servers">
          <span><Server :size="16" /> Servers</span>
          <strong>{{ servers.length }}</strong>
          <small>{{ servers.filter((server) => server.status === 'online').length }} online</small>
        </RouterLink>
        <RouterLink class="panel metric nav-metric" to="/admin/setup-jobs">
          <span><Activity :size="16" /> Setup</span>
          <strong>{{ jobs.length }}</strong>
          <small>{{ jobs.filter((job) => !job.finished_at).length }} в работе</small>
        </RouterLink>
      </div>

      <section class="panel">
        <div class="panel-header">
          <div>
            <h2><ScrollText :size="17" /> Последний аудит</h2>
            <p>Короткий хвост действий для быстрой диагностики.</p>
          </div>
          <RouterLink class="ghost-button" to="/admin/audit">Все логи</RouterLink>
        </div>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Время</th>
                <th>Action</th>
                <th>Actor</th>
                <th>Target</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="entry in audit" :key="entry.id">
                <td>{{ formatDate(entry.created_at) }}</td>
                <td>{{ entry.action }}</td>
                <td class="mono">{{ entry.actor_user_id || 'system' }}</td>
                <td>{{ entry.target_type || '—' }} <span class="muted mono">{{ entry.target_id || '' }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="panel">
        <div class="panel-header">
          <div>
            <h2>Серверы</h2>
            <p>Операционный статус и доступность для новых устройств.</p>
          </div>
        </div>
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Имя</th>
                <th>Статус</th>
                <th>Доступен</th>
                <th>Устройств</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="server in servers" :key="server.id">
                <td>{{ server.name }}</td>
                <td><StatusBadge :status="server.status" /></td>
                <td>{{ server.is_available_for_new_devices ? 'Да' : 'Нет' }}</td>
                <td>{{ server.active_device_count ?? 0 }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </section>
</template>

<style scoped lang="scss">
.nav-metric {
  color: inherit;

  span {
    display: flex;
    align-items: center;
    gap: 8px;
  }
}
</style>
