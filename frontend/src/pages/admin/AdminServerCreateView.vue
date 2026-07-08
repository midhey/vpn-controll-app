<script setup lang="ts">
import { Save } from '@lucide/vue'
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { adminApi } from '@/domains/admin/api'
import { errorMessage } from '@/shared/api/client'
import ErrorBanner from '@/shared/ui/ErrorBanner.vue'

const router = useRouter()
const pending = ref(false)
const error = ref('')
const form = reactive({
  name: '',
  public_host: '',
  public_port: 51820,
  agent_base_url: '',
  region_note: '',
  provider: '',
  agent_key_id: '',
  agent_secret: '',
  agent_allowed_ip_note: '',
  is_available_for_new_devices: true,
})

async function submit() {
  pending.value = true
  error.value = ''
  try {
    const created = await adminApi.servers.create({
      name: form.name,
      public_host: form.public_host,
      public_port: form.public_port || null,
      agent_base_url: form.agent_base_url,
      region_note: form.region_note || null,
      provider: form.provider || null,
      agent_key_id: form.agent_key_id || null,
      agent_secret: form.agent_secret || null,
      agent_allowed_ip_note: form.agent_allowed_ip_note || null,
      is_available_for_new_devices: form.is_available_for_new_devices,
    })
    await router.replace(`/admin/servers/${created.id}`)
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
        <h1>Создать сервер</h1>
        <p>Ручной server node с agent endpoint. Секрет вводится только в форму и не отображается после сохранения.</p>
      </div>
    </header>

    <ErrorBanner v-if="error" :message="error" />

    <section class="panel">
      <form class="panel-body form-grid cols-2" @submit.prevent="submit">
        <label class="field"><span>Name</span><input v-model.trim="form.name" required /></label>
        <label class="field"><span>Public host</span><input v-model.trim="form.public_host" required /></label>
        <label class="field"><span>Public port</span><input v-model.number="form.public_port" type="number" min="1" max="65535" /></label>
        <label class="field"><span>Agent base URL</span><input v-model.trim="form.agent_base_url" required placeholder="http://host:port" /></label>
        <label class="field"><span>Region</span><input v-model.trim="form.region_note" maxlength="200" /></label>
        <label class="field"><span>Provider</span><input v-model.trim="form.provider" maxlength="100" /></label>
        <label class="field"><span>Agent key id</span><input v-model.trim="form.agent_key_id" maxlength="100" /></label>
        <label class="field"><span>Agent secret</span><input v-model="form.agent_secret" type="password" maxlength="500" autocomplete="new-password" /></label>
        <label class="field"><span>Allowed IP note</span><input v-model.trim="form.agent_allowed_ip_note" maxlength="200" /></label>
        <label class="check-field"><input v-model="form.is_available_for_new_devices" type="checkbox" /> Доступен для новых устройств</label>
        <div class="page-actions">
          <RouterLink class="ghost-button" to="/admin/servers">Отмена</RouterLink>
          <button class="button" type="submit" :disabled="pending"><Save :size="16" /> Создать</button>
        </div>
      </form>
    </section>
  </section>
</template>
