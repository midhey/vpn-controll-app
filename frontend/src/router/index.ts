import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { bootstrap } from '@/domains/auth/session'
import AppShell from '@/app/AppShell.vue'
import LoginView from '@/pages/auth/LoginView.vue'
import DashboardView from '@/pages/user/DashboardView.vue'
import DevicesListView from '@/pages/user/DevicesListView.vue'
import DeviceCreateView from '@/pages/user/DeviceCreateView.vue'
import DeviceDetailView from '@/pages/user/DeviceDetailView.vue'
import ServersListView from '@/pages/user/ServersListView.vue'
import SupportView from '@/pages/user/SupportView.vue'
import AdminHomeView from '@/pages/admin/AdminHomeView.vue'
import AdminUsersView from '@/pages/admin/AdminUsersView.vue'
import AdminUserCreateView from '@/pages/admin/AdminUserCreateView.vue'
import AdminUserDetailView from '@/pages/admin/AdminUserDetailView.vue'
import AdminServersView from '@/pages/admin/AdminServersView.vue'
import AdminServerCreateView from '@/pages/admin/AdminServerCreateView.vue'
import AdminServerDetailView from '@/pages/admin/AdminServerDetailView.vue'
import AdminSetupJobsView from '@/pages/admin/AdminSetupJobsView.vue'
import AdminSetupJobCreateView from '@/pages/admin/AdminSetupJobCreateView.vue'
import AdminSetupJobDetailView from '@/pages/admin/AdminSetupJobDetailView.vue'
import AdminSupportSettingsView from '@/pages/admin/AdminSupportSettingsView.vue'
import AdminAuditLogsView from '@/pages/admin/AdminAuditLogsView.vue'

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    requiresAdmin?: boolean
  }
}

const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: LoginView },
  {
    path: '/',
    component: AppShell,
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: '/dashboard' },
      { path: 'dashboard', name: 'dashboard', component: DashboardView },
      { path: 'devices', name: 'devices', component: DevicesListView },
      { path: 'devices/new', name: 'device-create', component: DeviceCreateView },
      { path: 'devices/:id', name: 'device-detail', component: DeviceDetailView, props: true },
      { path: 'servers', name: 'servers', component: ServersListView },
      { path: 'support', name: 'support', component: SupportView },
      { path: 'admin', name: 'admin', component: AdminHomeView, meta: { requiresAdmin: true } },
      { path: 'admin/users', name: 'admin-users', component: AdminUsersView, meta: { requiresAdmin: true } },
      {
        path: 'admin/users/new',
        name: 'admin-user-create',
        component: AdminUserCreateView,
        meta: { requiresAdmin: true },
      },
      {
        path: 'admin/users/:id',
        name: 'admin-user-detail',
        component: AdminUserDetailView,
        props: true,
        meta: { requiresAdmin: true },
      },
      { path: 'admin/servers', name: 'admin-servers', component: AdminServersView, meta: { requiresAdmin: true } },
      {
        path: 'admin/servers/new',
        name: 'admin-server-create',
        component: AdminSetupJobCreateView,
        meta: { requiresAdmin: true },
      },
      {
        path: 'admin/servers/manual',
        name: 'admin-server-create-manual',
        component: AdminServerCreateView,
        meta: { requiresAdmin: true },
      },
      {
        path: 'admin/servers/:id',
        name: 'admin-server-detail',
        component: AdminServerDetailView,
        props: true,
        meta: { requiresAdmin: true },
      },
      {
        path: 'admin/setup-jobs',
        name: 'admin-setup-jobs',
        component: AdminSetupJobsView,
        meta: { requiresAdmin: true },
      },
      {
        path: 'admin/setup-jobs/new',
        name: 'admin-setup-job-create',
        component: AdminSetupJobCreateView,
        meta: { requiresAdmin: true },
      },
      {
        path: 'admin/setup-jobs/:id',
        name: 'admin-setup-job-detail',
        component: AdminSetupJobDetailView,
        props: true,
        meta: { requiresAdmin: true },
      },
      {
        path: 'admin/support-settings',
        name: 'admin-support-settings',
        component: AdminSupportSettingsView,
        meta: { requiresAdmin: true },
      },
      { path: 'admin/audit', name: 'admin-audit', component: AdminAuditLogsView, meta: { requiresAdmin: true } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const user = await bootstrap()

  if (to.name === 'login' && user) {
    return { name: 'dashboard' }
  }

  if (to.meta.requiresAuth && !user) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (to.meta.requiresAdmin && user?.role !== 'admin') {
    return { name: 'dashboard' }
  }

  return true
})
