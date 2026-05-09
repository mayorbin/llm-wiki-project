// frontend/src/router/index.ts
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/LoginView.vue'),
      meta: { requiresAuth: false },
    },
    {
      path: '/:projectId',
      component: () => import('@/views/AppShell.vue'),
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          name: 'Knowledge',
          component: () => import('@/views/KnowledgeBaseView.vue'),
        },
        {
          path: 'graph',
          name: 'Graph',
          component: () => import('@/views/GraphView.vue'),
        },
        {
          path: 'settings',
          name: 'Settings',
          component: () => import('@/views/SettingsView.vue'),
        },
      ],
    },
    { path: '/', redirect: '/default' },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

// 导航守卫——未登录跳 /login
router.beforeEach(async (to) => {
  if (to.path === '/login') return true
  const { useAuthStore } = await import('@/stores/auth')
  const auth = useAuthStore()
  if (!auth.isAuthenticated) {
    await auth.initialize()
  }
  if (!auth.isAuthenticated && to.meta.requiresAuth !== false) {
    return { name: 'Login', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
