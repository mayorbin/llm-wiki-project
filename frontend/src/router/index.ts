// frontend/src/router/index.ts
/**
 * Vue Router 路由配置。
 *
 * 路由结构：
 *   /login             — 登录页
 *   /                  — 首页（有项目跳第一个，无项目显示引导）
 *   /:projectId        — 知识库主页
 *   /:projectId/graph  — 知识图谱
 *   /:projectId/settings — 项目设置
 */
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
      path: '/',
      name: 'Home',
      component: () => import('@/views/HomeView.vue'),
      meta: { requiresAuth: true },
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
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

// 导航守卫——未登录跳 /login，已登录无项目则留在首页
router.beforeEach(async (to) => {
  if (to.path === '/login') return true

  const { useAuthStore } = await import('@/stores/auth')
  const auth = useAuthStore()

  if (!auth.isAuthenticated) {
    await auth.initialize()
  }

  // F5刷新后 token 有效但 projects 未加载——需重新拉取
  if (auth.isAuthenticated && (!auth.projects || auth.projects.length === 0)) {
    await auth.initialize()
  }

  if (!auth.isAuthenticated && to.meta.requiresAuth !== false) {
    return { name: 'Login', query: { redirect: to.fullPath } }
  }

  // 已登录且访问根路径：有项目则跳转第一个项目
  if (to.path === '/' && auth.isAuthenticated) {
    const lastProject = localStorage.getItem('last_project')
    const projects = auth.projects || []

    if (lastProject && projects.some((p: any) => p.id === lastProject)) {
      return `/${lastProject}`
    }
    if (projects.length > 0) {
      return `/${projects[0].id}`
    }
  }

  // 检查目标 projectId 是否有效，同时保存 last_project
  const targetProjectId = to.params.projectId as string | undefined
  if (targetProjectId && auth.isAuthenticated) {
    const projects = auth.projects || []
    if (targetProjectId === 'default' || !projects.some((p: any) => p.id === targetProjectId)) {
      return '/'
    }
    localStorage.setItem('last_project', targetProjectId)
  }

  return true
})

export default router
