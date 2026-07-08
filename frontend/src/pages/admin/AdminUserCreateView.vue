<script setup lang="ts">
import { Save } from '@lucide/vue'
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { adminApi } from '@/domains/admin/api'
import { errorMessage } from '@/shared/api/client'
import type { UserRole } from '@/shared/api/types'
import ErrorBanner from '@/shared/ui/ErrorBanner.vue'

const router = useRouter()
const pending = ref(false)
const error = ref('')
const form = reactive({
  login: '',
  display_name: '',
  password: '',
  role: 'user' as UserRole,
  telegram_username: '',
  device_limit: 3,
  device_limit_unlimited: false,
  show_server_support: true,
  free_access: false,
  note: '',
})

async function submit() {
  pending.value = true
  error.value = ''
  try {
    const created = await adminApi.users.create({
      login: form.login,
      display_name: form.display_name,
      password: form.password,
      role: form.role,
      telegram_username: form.telegram_username || null,
      device_limit: form.device_limit_unlimited ? null : form.device_limit,
      device_limit_unlimited: form.device_limit_unlimited,
      show_server_support: form.show_server_support,
      free_access: form.free_access,
      note: form.note || null,
    })
    await router.replace(`/admin/users/${created.id}`)
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <h1>Создать пользователя</h1>
        <p>Минимальный набор: login, display name и первичный пароль.</p>
      </div>
    </header>

    <ErrorBanner v-if="error" :message="error" />

    <section class="panel">
      <form class="panel-body form-grid cols-2" @submit.prevent="submit">
        <label class="field"><span>Login</span><input v-model.trim="form.login" required maxlength="64" /></label>
        <label class="field"><span>Display name</span><input v-model.trim="form.display_name" required maxlength="100" /></label>
        <label class="field"><span>Password</span><input v-model="form.password" type="password" required minlength="6" /></label>
        <label class="field">
          <span>Role</span>
          <select v-model="form.role">
            <option value="user">user</option>
            <option value="admin">admin</option>
          </select>
        </label>
        <label class="field"><span>Telegram</span><input v-model.trim="form.telegram_username" maxlength="64" placeholder="username без @" /></label>
        <label class="field"><span>Device limit</span><input v-model.number="form.device_limit" type="number" min="0" :disabled="form.device_limit_unlimited" /></label>
        <label class="check-field"><input v-model="form.device_limit_unlimited" type="checkbox" /> Без лимита устройств</label>
        <label class="check-field"><input v-model="form.show_server_support" type="checkbox" /> Показывать поддержку</label>
        <label class="check-field"><input v-model="form.free_access" type="checkbox" /> Free access</label>
        <label class="field"><span>Note</span><textarea v-model.trim="form.note" rows="3" maxlength="500"></textarea></label>
        <div class="page-actions">
          <RouterLink class="ghost-button" to="/admin/users">Отмена</RouterLink>
          <button class="button" type="submit" :disabled="pending"><Save :size="16" /> Создать</button>
        </div>
      </form>
    </section>
  </section>
</template>
