<script setup lang="ts">
import { RotateCw, Save } from '@lucide/vue'
import { onMounted, reactive, ref } from 'vue'
import { adminApi } from '@/domains/admin/api'
import { errorMessage } from '@/shared/api/client'
import type { SupportSettingsOut } from '@/shared/api/types'
import { formatDate } from '@/shared/lib/format'
import ErrorBanner from '@/shared/ui/ErrorBanner.vue'
import LoadingState from '@/shared/ui/LoadingState.vue'

const settings = ref<SupportSettingsOut | null>(null)
const loading = ref(true)
const pending = ref(false)
const error = ref('')
const notice = ref('')
const form = reactive({
  title: '',
  description: '',
  sbp_phone: '',
  bank_name: '',
  extra_contact: '',
  monthly_cost_amount: 0,
  reserve_amount: 0,
  is_enabled: true,
})

function assignForm(value: SupportSettingsOut) {
  Object.assign(form, {
    title: value.title,
    description: value.description,
    sbp_phone: value.sbp_phone || '',
    bank_name: value.bank_name || '',
    extra_contact: value.extra_contact || '',
    monthly_cost_amount: value.monthly_cost_amount ?? 0,
    reserve_amount: value.reserve_amount ?? 0,
    is_enabled: value.is_enabled,
  })
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    settings.value = await adminApi.support.getSettings()
    assignForm(settings.value)
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
    settings.value = await adminApi.support.updateSettings({
      title: form.title,
      description: form.description,
      sbp_phone: form.sbp_phone || null,
      bank_name: form.bank_name || null,
      extra_contact: form.extra_contact || null,
      monthly_cost_amount: form.monthly_cost_amount || null,
      reserve_amount: form.reserve_amount || null,
      is_enabled: form.is_enabled,
    })
    assignForm(settings.value)
    notice.value = 'Настройки поддержки сохранены'
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    pending.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="page">
    <header class="page-header">
      <div>
        <h1>Support settings</h1>
        <p v-if="settings">Обновлено: {{ formatDate(settings.updated_at) }}</p>
      </div>
      <div class="page-actions">
        <button class="ghost-button" type="button" @click="load"><RotateCw :size="16" /> Обновить</button>
      </div>
    </header>

    <LoadingState v-if="loading" />
    <ErrorBanner v-else-if="error" :message="error" />
    <div v-if="notice" class="alert">{{ notice }}</div>

    <section v-if="!loading" class="panel">
      <form class="panel-body form-grid cols-2" @submit.prevent="save">
        <label class="check-field"><input v-model="form.is_enabled" type="checkbox" /> Включить поддержку</label>
        <label class="field"><span>Title</span><input v-model.trim="form.title" required maxlength="100" /></label>
        <label class="field"><span>Description</span><textarea v-model.trim="form.description" rows="4" maxlength="1000"></textarea></label>
        <label class="field"><span>SBP phone</span><input v-model.trim="form.sbp_phone" /></label>
        <label class="field"><span>Bank name</span><input v-model.trim="form.bank_name" /></label>
        <label class="field"><span>Extra contact</span><input v-model.trim="form.extra_contact" /></label>
        <label class="field"><span>Monthly cost</span><input v-model.number="form.monthly_cost_amount" type="number" min="0" /></label>
        <label class="field"><span>Reserve amount</span><input v-model.number="form.reserve_amount" type="number" min="0" /></label>
        <div class="page-actions">
          <button class="button" type="submit" :disabled="pending"><Save :size="16" /> Сохранить</button>
        </div>
      </form>
    </section>
  </section>
</template>
