<script setup lang="ts">
import { Plus, RotateCw } from '@lucide/vue'
import { onMounted, ref } from 'vue'
import { adminApi } from '@/domains/admin/api'
import { errorMessage } from '@/shared/api/client'
import type { AdminUserOut } from '@/shared/api/types'
import { formatDate } from '@/shared/lib/format'
import EmptyState from '@/shared/ui/EmptyState.vue'
import ErrorBanner from '@/shared/ui/ErrorBanner.vue'
import LoadingState from '@/shared/ui/LoadingState.vue'
import StatusBadge from '@/shared/ui/StatusBadge.vue'

const users = ref<AdminUserOut[]>([])
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    users.value = await adminApi.users.list()
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
        <h1>Users</h1>
        <p>Создание, редактирование, лимиты, доступ и пользовательские устройства.</p>
      </div>
      <div class="page-actions">
        <button class="ghost-button" type="button" @click="load"><RotateCw :size="16" /> Обновить</button>
        <RouterLink class="button" to="/admin/users/new"><Plus :size="17" /> Создать</RouterLink>
      </div>
    </header>

    <section class="panel">
      <LoadingState v-if="loading" />
      <ErrorBanner v-else-if="error" :message="error" />
      <EmptyState v-else-if="users.length === 0" title="Пользователей нет" />
      <div v-else class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Login</th>
              <th>Role</th>
              <th>Status</th>
              <th>Devices</th>
              <th>Support</th>
              <th>Created</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="user in users" :key="user.id">
              <td>
                <strong>{{ user.display_name }}</strong>
                <div class="muted">{{ user.login }}{{ user.telegram_username ? ` · @${user.telegram_username}` : '' }}</div>
              </td>
              <td>{{ user.role }}</td>
              <td><StatusBadge :status="user.is_active ? 'active' : 'disabled'" /></td>
              <td>{{ user.active_device_count ?? 0 }} / {{ user.device_limit_unlimited ? '∞' : user.device_limit ?? 0 }}</td>
              <td>{{ user.show_server_support && !user.free_access ? 'Да' : 'Нет' }}</td>
              <td>{{ formatDate(user.created_at) }}</td>
              <td><RouterLink class="ghost-button" :to="`/admin/users/${user.id}`">Открыть</RouterLink></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </section>
</template>
