<script setup lang="ts">
import { Save } from '@lucide/vue'
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { adminApi } from '@/domains/admin/api'
import { errorMessage } from '@/shared/api/client'
import type { AuthMethod } from '@/shared/api/types'
import BaseSwitch from '@/shared/ui/BaseSwitch.vue'
import ErrorBanner from '@/shared/ui/ErrorBanner.vue'

const router = useRouter()
const pending = ref(false)
const error = ref('')
const form = reactive({
  server_name: '',
  host: '',
  ssh_port: 22,
  ssh_username: 'root',
  auth_method: 'password' as AuthMethod,
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
        <h1>Установить сервер</h1>
        <p>Панель подключится по SSH, установит агент и сама добавит сервер в систему.</p>
      </div>
    </header>

    <ErrorBanner v-if="error" :message="error" />

    <section class="panel">
      <form class="panel-body form-grid cols-2" @submit.prevent="submit">
        <p class="form-note cols-2">
          SSH-пароль нужен только на время установки. Он не записывается в базу, файлы или журналы и удаляется
          из памяти backend сразу после завершения или отмены задачи.
        </p>
        <details class="setup-prerequisites cols-2">
          <summary>Что подготовить на сервере перед установкой</summary>
          <div class="setup-prerequisites__body">
            <ol>
              <li>Linux x86_64 с systemd и доступом по SSH.</li>
              <li>
                Пользователь <code>root</code> с паролем — рекомендуемый вариант. Для другого пользователя нужен
                <code>sudo</code>, использующий тот же пароль.
              </li>
              <li>Docker должен быть установлен и запущен.</li>
              <li>Контейнер AmneziaWG <code>amnezia-awg2</code> должен быть запущен.</li>
              <li>Откройте TCP-порт агента <code>8090</code> только для IP сервера с этой панелью.</li>
            </ol>
            <p>Быстрая проверка на сервере:</p>
            <pre><code>uname -m
docker info
docker ps --filter name=amnezia-awg2</code></pre>
          </div>
        </details>
        <label class="field"><span>Название сервера</span><input v-model.trim="form.server_name" required /></label>
        <label class="field"><span>IP или домен сервера</span><input v-model.trim="form.host" required /></label>
        <label class="field"><span>SSH-порт</span><input v-model.number="form.ssh_port" type="number" min="1" max="65535" /></label>
        <label class="field"><span>SSH-пользователь</span><input v-model.trim="form.ssh_username" required /></label>
        <label class="field">
          <span>SSH-пароль</span>
          <input v-model="form.secret" required type="password" autocomplete="new-password" />
        </label>
        <label class="field"><span>Регион</span><input v-model.trim="form.region_note" /></label>
        <BaseSwitch v-model="form.install_awg">Проверить существующее AWG-окружение</BaseSwitch>
        <BaseSwitch v-model="form.available_for_new_devices">Доступен для новых устройств</BaseSwitch>
        <BaseSwitch v-model="form.verify_before_install">Выполнить SSH preflight до загрузки файлов</BaseSwitch>
        <div class="page-actions">
          <RouterLink class="ghost-button" to="/admin/servers">Отмена</RouterLink>
          <button class="button" type="submit" :disabled="pending"><Save :size="16" /> Установить</button>
        </div>
      </form>
    </section>
  </section>
</template>

<style scoped lang="scss">
.form-note {
  margin: 0;
  padding: 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-small);
  color: var(--color-text-muted);
  background: var(--color-surface-inset);
  line-height: 1.5;
}

.setup-prerequisites {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-small);
  background: var(--color-surface-inset);

  summary {
    padding: 12px;
    color: var(--color-text-strong);
    font-weight: 800;
    cursor: pointer;
  }

  &[open] summary {
    border-bottom: 1px solid var(--color-border);
  }
}

.setup-prerequisites__body {
  padding: 4px 16px 16px;
  color: var(--color-text-muted);
  line-height: 1.5;

  ol {
    padding-left: 20px;
  }

  code {
    color: var(--color-code-text);
  }

  pre {
    overflow-x: auto;
    margin: 8px 0 0;
    padding: 12px;
    border-radius: var(--radius-small);
    color: var(--color-code-text);
    background: var(--color-code-background);
  }
}
</style>
