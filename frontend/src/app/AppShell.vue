<script setup lang="ts">
import {
  Activity,
  ClipboardList,
  CreditCard,
  Gauge,
  HardDrive,
  LogOut,
  Plus,
  ScrollText,
  Server,
  Settings,
  Shield,
  Users,
} from '@lucide/vue'
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { useSession } from '@/domains/auth/session'

const session = useSession()
const router = useRouter()
const route = useRoute()

const userNav = [
  { to: '/dashboard', label: 'Панель', icon: Gauge },
  { to: '/devices', label: 'Устройства', icon: HardDrive },
  { to: '/devices/new', label: 'Выпуск', icon: Plus },
  { to: '/servers', label: 'Серверы', icon: Server },
  { to: '/support', label: 'Поддержка', icon: CreditCard },
]

const adminNav = [
  { to: '/admin', label: 'Admin', icon: Shield },
  { to: '/admin/users', label: 'Users', icon: Users },
  { to: '/admin/servers', label: 'Servers', icon: Server },
  { to: '/admin/setup-jobs', label: 'Setup', icon: Activity },
  { to: '/admin/support-settings', label: 'Support', icon: Settings },
  { to: '/admin/audit', label: 'Audit', icon: ScrollText },
]

const isAdminArea = computed(() => route.path.startsWith('/admin'))

async function logout() {
  await session.logout()
  await router.replace({ name: 'login' })
}
</script>

<template>
  <div class="app-shell" :class="{ 'is-admin-area': isAdminArea }">
    <aside class="sidebar">
      <RouterLink to="/dashboard" class="brand" aria-label="Подсос VPN">
        <span class="brand-mark"><Shield :size="20" /></span>
        <span>
          <strong>Подсос VPN</strong>
          <small>control</small>
        </span>
      </RouterLink>

      <nav class="nav-group" aria-label="Основная навигация">
        <RouterLink v-for="item in userNav" :key="item.to" :to="item.to" class="nav-link">
          <component :is="item.icon" :size="18" />
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>

      <nav v-if="session.isAdmin.value" class="nav-group admin-nav" aria-label="Администрирование">
        <div class="nav-caption"><ClipboardList :size="14" /> Admin</div>
        <RouterLink v-for="item in adminNav" :key="item.to" :to="item.to" class="nav-link">
          <component :is="item.icon" :size="18" />
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>

      <div class="sidebar-footer">
        <div class="user-chip">
          <span class="avatar">{{ session.user.value?.display_name?.slice(0, 1) || '?' }}</span>
          <span>
            <strong>{{ session.user.value?.display_name }}</strong>
            <small>{{ session.user.value?.login }} · {{ session.user.value?.role }}</small>
          </span>
        </div>
        <button class="icon-button" type="button" aria-label="Выйти" @click="logout">
          <LogOut :size="18" />
        </button>
      </div>
    </aside>

    <main class="main-surface">
      <RouterView />
    </main>

    <nav class="mobile-nav" aria-label="Мобильная навигация">
      <RouterLink v-for="item in userNav.slice(0, 4)" :key="item.to" :to="item.to" class="mobile-link">
        <component :is="item.icon" :size="18" />
        <span>{{ item.label }}</span>
      </RouterLink>
      <RouterLink v-if="session.isAdmin.value" to="/admin" class="mobile-link">
        <Shield :size="18" />
        <span>Admin</span>
      </RouterLink>
    </nav>
  </div>
</template>
