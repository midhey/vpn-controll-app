<script setup lang="ts">
import { Lock, Shield } from '@lucide/vue'
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSession } from '@/domains/auth/session'
import { errorMessage } from '@/shared/api/client'
import ErrorBanner from '@/shared/ui/ErrorBanner.vue'

const router = useRouter()
const route = useRoute()
const session = useSession()

const form = reactive({
  login: '',
  password: '',
})
const pending = ref(false)
const error = ref('')

async function submit() {
  pending.value = true
  error.value = ''
  try {
    await session.login({ login: form.login, password: form.password })
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard'
    await router.replace(redirect)
  } catch (err) {
    error.value = errorMessage(err)
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-panel">
      <div class="brand login-brand">
        <span class="brand-mark"><Shield :size="20" /></span>
        <span>
          <strong>Подсос VPN</strong>
          <small>secure control panel</small>
        </span>
      </div>

      <div class="login-copy">
        <h1>Вход в панель</h1>
        <p>Cookie-сессия будет использована для всех API-запросов.</p>
      </div>

      <ErrorBanner v-if="error" :message="error" />

      <form class="form-grid" @submit.prevent="submit">
        <label class="field">
          <span>Логин</span>
          <input v-model.trim="form.login" autocomplete="username" required autofocus />
        </label>
        <label class="field">
          <span>Пароль</span>
          <input v-model="form.password" type="password" autocomplete="current-password" required />
        </label>
        <button class="button" type="submit" :disabled="pending">
          <Lock :size="17" />
          {{ pending ? 'Проверяю…' : 'Войти' }}
        </button>
      </form>
    </section>
  </main>
</template>

<style scoped lang="scss">
.login-page {
  display: grid;
  min-height: 100vh;
  place-items: center;
  padding: 24px;
}

.login-panel {
  display: grid;
  gap: 18px;
  width: min(430px, 100%);
  padding: 24px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-medium);
  background: var(--color-auth-panel-background);
  box-shadow: var(--shadow-surface);
}

.login-brand {
  padding: 0 0 16px;
}

.login-copy {
  h1 {
    margin: 0;
    color: var(--color-text-strong);
    font-size: 30px;
    line-height: 1.1;
  }

  p {
    margin: 8px 0 0;
    color: var(--color-text-muted);
    font-size: 14px;
    line-height: 1.5;
  }
}
</style>
