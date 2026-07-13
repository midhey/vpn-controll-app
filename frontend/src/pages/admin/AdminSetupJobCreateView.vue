<script setup lang="ts">
import { Save } from '@lucide/vue'
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { adminApi } from '@/domains/admin/api'
import { errorMessage } from '@/shared/api/client'
import type { AuthMethod } from '@/shared/api/types'
import ErrorBanner from '@/shared/ui/ErrorBanner.vue'

const router = useRouter()
const pending = ref(false)
const error = ref('')
const form = reactive({
  server_name: '',
  host: '',
  ssh_port: 22,
  ssh_username: 'root',
  auth_method: 'ssh_key' as AuthMethod,
  secret: '',
  region_note: '',
  install_awg: true,
  available_for_new_devices: true,
  verify_before_install: true,
})

async function submit() {
  pending.value = true
  error.value = ''
  try {
    const job = await adminApi.setupJobs.create({
      server_name: form.server_name,
      host: form.host,
      ssh_port: form.ssh_port,
      ssh_username: form.ssh_username,
      auth_method: form.auth_method,
      secret: form.secret,
      region_note: form.region_note || null,
      install_awg: form.install_awg,
      available_for_new_devices: form.available_for_new_devices,
      verify_before_install: form.verify_before_install,
    })
    await router.replace(`/admin/setup-jobs/${job.id}`)
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
        <h1>Создать setup job</h1>
        <p>SSH-секрет используется только для установки агента, шифруется при хранении и не возвращается API.</p>
      </div>
    </header>

    <ErrorBanner v-if="error" :message="error" />

    <section class="panel">
      <form class="panel-body form-grid cols-2" @submit.prevent="submit">
        <p class="form-note cols-2">
          Используйте одноразовый SSH key или временный пароль. После установки отзовите этот доступ на VPS.
          Для ключа используйте временный ключ без passphrase: passphrase пока не поддерживается setup-runner'ом.
        </p>
        <label class="field"><span>Server name</span><input v-model.trim="form.server_name" required /></label>
        <label class="field"><span>Host</span><input v-model.trim="form.host" required /></label>
        <label class="field"><span>SSH port</span><input v-model.number="form.ssh_port" type="number" min="1" max="65535" /></label>
        <label class="field"><span>SSH username</span><input v-model.trim="form.ssh_username" required /></label>
        <label class="field">
          <span>Auth method</span>
          <select v-model="form.auth_method">
            <option value="ssh_key">ssh_key</option>
            <option value="password">password</option>
          </select>
        </label>
        <label class="field"><span>Secret</span><textarea v-model="form.secret" required rows="5" autocomplete="off"></textarea></label>
        <label class="field"><span>Region</span><input v-model.trim="form.region_note" /></label>
        <label class="check-field"><input v-model="form.install_awg" type="checkbox" /> Проверить существующее AWG-окружение</label>
        <label class="check-field"><input v-model="form.available_for_new_devices" type="checkbox" /> Доступен для новых устройств</label>
        <label class="check-field"><input v-model="form.verify_before_install" type="checkbox" /> Выполнить SSH preflight до загрузки файлов</label>
        <div class="page-actions">
          <RouterLink class="ghost-button" to="/admin/setup-jobs">Отмена</RouterLink>
          <button class="button" type="submit" :disabled="pending"><Save :size="16" /> Создать</button>
        </div>
      </form>
    </section>
  </section>
</template>

<style scoped lang="scss">
.form-note {
  margin: 0;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--muted);
  background: rgba(10, 16, 32, 0.52);
  line-height: 1.5;
}
</style>
