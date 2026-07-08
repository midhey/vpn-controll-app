import { computed, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError, setUnauthorizedHandler } from '@/shared/api/client'
import type { LoginIn, UserOut } from '@/shared/api/types'
import * as authApi from './api'

type BootstrapState = 'idle' | 'loading' | 'ready'

const state = reactive<{
  user: UserOut | null
  bootstrapState: BootstrapState
  error: string | null
}>({
  user: null,
  bootstrapState: 'idle',
  error: null,
})

let bootstrapPromise: Promise<UserOut | null> | null = null

export function useSession() {
  const router = useRouter()

  setUnauthorizedHandler(() => {
    clearSession()
    if (router.currentRoute.value.name !== 'login') {
      void router.replace({ name: 'login', query: { redirect: router.currentRoute.value.fullPath } })
    }
  })

  return {
    state,
    user: computed(() => state.user),
    isAuthenticated: computed(() => Boolean(state.user)),
    isAdmin: computed(() => state.user?.role === 'admin'),
    isBootstrapping: computed(() => state.bootstrapState === 'loading'),
    bootstrap,
    login: loginUser,
    logout: logoutUser,
    clear: clearSession,
  }
}

export async function bootstrap(): Promise<UserOut | null> {
  if (state.bootstrapState === 'ready') return state.user
  if (bootstrapPromise) return bootstrapPromise

  state.bootstrapState = 'loading'
  state.error = null
  bootstrapPromise = authApi
    .session()
    .then((session) => {
      state.user = session.user
      return session.user
    })
    .catch((error: unknown) => {
      state.user = null
      if (error instanceof ApiError && error.status === 401) return null
      state.error = error instanceof Error ? error.message : 'Не удалось проверить сессию'
      return null
    })
    .finally(() => {
      state.bootstrapState = 'ready'
      bootstrapPromise = null
    })

  return bootstrapPromise
}

async function loginUser(payload: LoginIn): Promise<UserOut> {
  state.error = null
  const response = await authApi.login(payload)
  state.user = response.user
  state.bootstrapState = 'ready'
  return response.user
}

async function logoutUser(): Promise<void> {
  try {
    await authApi.logout()
  } finally {
    clearSession()
  }
}

function clearSession() {
  state.user = null
  state.bootstrapState = 'ready'
}
