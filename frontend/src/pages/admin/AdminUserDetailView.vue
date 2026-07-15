<script setup lang="ts">
import { KeyRound, Power, RotateCw, Save } from '@lucide/vue'
import { onMounted, reactive, ref } from 'vue'
import { adminApi } from '@/domains/admin/api'
import { errorMessage } from '@/shared/api/client'
import type { AdminUserOut, ContributionOut, DeviceOut, UserRole } from '@/shared/api/types'
import { formatDate, formatMoney } from '@/shared/lib/format'
import BaseSelect from '@/shared/ui/BaseSelect.vue'
import EmptyState from '@/shared/ui/EmptyState.vue'
import ErrorBanner from '@/shared/ui/ErrorBanner.vue'
import LoadingState from '@/shared/ui/LoadingState.vue'
import type { SelectOption } from '@/shared/ui/select'
import StatusBadge from '@/shared/ui/StatusBadge.vue'

const roleOptions: SelectOption[] = [
  { value: 'user', label: 'user' },
  { value: 'admin', label: 'admin' },
]

const props = defineProps<{ id: string }>()

const user = ref<AdminUserOut | null>(null)
const devices = ref<DeviceOut[]>([])
const contributions = ref<ContributionOut[]>([])
const loading = ref(true)
const pending = ref(false)
const error = ref('')
const notice = ref('')
const resetPassword = ref('')
const contributionForm = reactive({
  amount: 0,
  currency: 'RUB',
  period_label: '',
  comment: '',
})
const form = reactive({
  display_name: '',
  role: 'user' as UserRole,
  telegram_username: '',
  device_limit: 0,
  device_limit_unlimited: false,
  show_server_support: true,
  free_access: false,
  note: '',
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [userResult, deviceResult, contributionResult] = await Promise.all([
      adminApi.users.get(props.id),
      adminApi.users.devices(props.id),
      adminApi.users.contributions(props.id),
    ])
    user.value = userResult
    devices.value = deviceResult
    contributions.value = contributionResult
    Object.assign(form, {
      display_name: userResult.display_name,
      role: userResult.role,
      telegram_username: userResult.telegram_username || '',
      device_limit: userResult.device_limit ?? 0,
      device_limit_unlimited: userResult.device_limit_unlimited,
      show_server_support: userResult.show_server_support,
      free_access: userResult.free_access,
      note: userResult.note || '',
    })
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    loading.value = false
  }
}

async function save() {
  pending.value = true
  error.value = ''
  notice.value = ''
  try {
    user.value = await adminApi.users.update(props.id, {
      display_name: form.display_name,
      role: form.role,
      telegram_username: form.telegram_username || null,
      device_limit: form.device_limit_unlimited ? null : form.device_limit,
      device_limit_unlimited: form.device_limit_unlimited,
      show_server_support: form.show_server_support,
      free_access: form.free_access,
      note: form.note || null,
    })
    notice.value = 'Пользователь сохранён'
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    pending.value = false
  }
}

async function toggleActive() {
  if (!user.value) return
  pending.value = true
  error.value = ''
  try {
    user.value = user.value.is_active
      ? await adminApi.users.disable(props.id)
      : await adminApi.users.enable(props.id)
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    pending.value = false
  }
}

async function resetUserPassword() {
  if (!resetPassword.value) return
  pending.value = true
  error.value = ''
  notice.value = ''
  try {
    await adminApi.users.resetPassword(props.id, { password: resetPassword.value })
    resetPassword.value = ''
    notice.value = 'Пароль сброшен'
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    pending.value = false
  }
}

async function recordContribution() {
  if (contributionForm.amount <= 0) return
  pending.value = true
  error.value = ''
  try {
    const contribution = await adminApi.users.recordContribution(props.id, {
      amount: contributionForm.amount,
      currency: contributionForm.currency,
      period_label: contributionForm.period_label || null,
      comment: contributionForm.comment || null,
    })
    contributions.value = [contribution, ...contributions.value]
    Object.assign(contributionForm, { amount: 0, period_label: '', comment: '' })
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    pending.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="page is-wide">
    <header class="page-header">
      <div>
        <h1>{{ user?.display_name || 'User' }}</h1>
        <p v-if="user">{{ user.login }} · {{ user.role }} · создан {{ formatDate(user.created_at) }}</p>
      </div>
      <div class="page-actions">
        <button class="ghost-button" type="button" @click="load"><RotateCw :size="16" /> Обновить</button>
        <button v-if="user" class="danger-button" type="button" :disabled="pending" @click="toggleActive">
          <Power :size="16" /> {{ user.is_active ? 'Disable' : 'Enable' }}
        </button>
      </div>
    </header>

    <LoadingState v-if="loading" />
    <ErrorBanner v-else-if="error" :message="error" />
    <div v-if="notice" class="alert">{{ notice }}</div>

    <template v-if="!loading && user">
      <div class="grid cols-2">
        <section class="panel">
          <div class="panel-header">
            <div>
              <h2>Поля пользователя</h2>
              <p>Изменения применяются PATCH-запросом.</p>
            </div>
            <StatusBadge :status="user.is_active ? 'active' : 'disabled'" />
          </div>
          <form class="panel-body form-grid cols-2" @submit.prevent="save">
            <label class="field"><span>Display name</span><input v-model.trim="form.display_name" required /></label>
            <BaseSelect id="user-role" v-model="form.role" name="role" label="Role" :options="roleOptions" />
            <label class="field"><span>Telegram</span><input v-model.trim="form.telegram_username" /></label>
            <label class="field"><span>Device limit</span><input v-model.number="form.device_limit" type="number" min="0" :disabled="form.device_limit_unlimited" /></label>
            <label class="check-field"><input v-model="form.device_limit_unlimited" type="checkbox" /> Без лимита устройств</label>
            <label class="check-field"><input v-model="form.show_server_support" type="checkbox" /> Показывать поддержку</label>
            <label class="check-field"><input v-model="form.free_access" type="checkbox" /> Free access</label>
            <label class="field"><span>Note</span><textarea v-model.trim="form.note" rows="3"></textarea></label>
            <div class="page-actions">
              <button class="button" type="submit" :disabled="pending"><Save :size="16" /> Сохранить</button>
            </div>
          </form>
        </section>

        <section class="panel">
          <div class="panel-header">
            <div>
              <h2>Reset password</h2>
              <p>Пароль не возвращается backend и не сохраняется во frontend.</p>
            </div>
          </div>
          <form class="panel-body form-grid" @submit.prevent="resetUserPassword">
            <label class="field"><span>Новый пароль</span><input v-model="resetPassword" type="password" minlength="6" autocomplete="new-password" /></label>
            <button class="button" type="submit" :disabled="pending || resetPassword.length < 6"><KeyRound :size="16" /> Reset</button>
          </form>
        </section>
      </div>

      <div class="grid cols-2">
        <section class="panel">
          <div class="panel-header">
            <div>
              <h2>Устройства пользователя</h2>
              <p>{{ devices.length }} записей</p>
            </div>
          </div>
          <EmptyState v-if="devices.length === 0" title="Нет устройств" />
          <div v-else class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Имя</th>
                  <th>Статус</th>
                  <th>Сервер</th>
                  <th>Создано</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="device in devices" :key="device.id">
                  <td>{{ device.name }}</td>
                  <td><StatusBadge :status="device.status" /></td>
                  <td>{{ device.server_name || device.server_node_id }}</td>
                  <td>{{ formatDate(device.created_at) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="panel">
          <div class="panel-header">
            <div>
              <h2>Support contributions</h2>
              <p>Запись и история взносов пользователя.</p>
            </div>
          </div>
          <form class="panel-body form-grid cols-2" @submit.prevent="recordContribution">
            <label class="field"><span>Amount</span><input v-model.number="contributionForm.amount" type="number" min="0" step="0.01" /></label>
            <label class="field"><span>Currency</span><input v-model.trim="contributionForm.currency" maxlength="3" /></label>
            <label class="field"><span>Period</span><input v-model.trim="contributionForm.period_label" /></label>
            <label class="field"><span>Comment</span><input v-model.trim="contributionForm.comment" /></label>
            <button class="button" type="submit" :disabled="pending || contributionForm.amount <= 0">Записать</button>
          </form>
          <div class="table-wrap">
            <table class="data-table">
              <thead>
                <tr>
                  <th>Дата</th>
                  <th>Сумма</th>
                  <th>Период</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in contributions" :key="item.id">
                  <td>{{ formatDate(item.recorded_at) }}</td>
                  <td>{{ formatMoney(item.amount, item.currency) }}</td>
                  <td>{{ item.period_label || '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </template>
  </section>
</template>
