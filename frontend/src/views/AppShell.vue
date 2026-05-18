<script setup lang="ts">
/**
 * 应用外壳——深色侧边栏 + SVG Logo + 项目切换 + 导航。
 */
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const currentProject = computed(() =>
  auth.projects.find((p: any) => p.id === route.params.projectId)
)

const navItems = [
  { path: '', label: '知识库', icon: 'book' },
  { path: 'graph', label: '知识图谱', icon: 'graph' },
  { path: 'settings', label: '设置', icon: 'settings' },
]

function switchProject(projectId: string) {
  router.push(`/${projectId}`)
}

function logout() {
  auth.logout()
  router.push('/login')
}

function getNavClass(path: string): string {
  const projectId = route.params.projectId as string
  const currentFull = `/${projectId}/${path}`.replace(/\/$/, '')
  const routeFull = route.path.replace(/\/$/, '')
  if (path === '' && routeFull === `/${projectId}`) return 'active'
  if (path !== '' && routeFull === currentFull) return 'active'
  return ''
}
</script>

<template>
  <div class="shell">
    <!-- 深色侧边栏 -->
    <aside class="sidebar">
      <!-- Logo -->
      <div class="logo-section">
        <svg class="logo-icon" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect width="40" height="40" rx="10" fill="url(#logo-grad)"/>
          <path d="M12 14h16v2H12zM12 19h12v2H12zM12 24h14v2H12z" fill="#fff"/>
          <circle cx="28" cy="15" r="1.5" fill="rgba(255,255,255,0.6)"/>
          <circle cx="30" cy="15" r="1.5" fill="rgba(255,255,255,0.6)"/>
          <circle cx="28" cy="20" r="1.5" fill="rgba(255,255,255,0.6)"/>
          <circle cx="30" cy="20" r="1.5" fill="rgba(255,255,255,0.6)"/>
          <circle cx="28" cy="25" r="1.5" fill="rgba(255,255,255,0.6)"/>
          <circle cx="30" cy="25" r="1.5" fill="rgba(255,255,255,0.6)"/>
          <defs>
            <linearGradient id="logo-grad" x1="0" y1="0" x2="40" y2="40">
              <stop stop-color="#D97706"/>
              <stop offset="1" stop-color="#EA580C"/>
            </linearGradient>
          </defs>
        </svg>
        <div class="logo-text">
          <span class="logo-title">LLM Wiki</span>
          <span class="logo-subtitle">知识从不丢失</span>
        </div>
      </div>

      <!-- 项目切换 -->
      <div class="project-area">
        <select
          :value="route.params.projectId"
          @change="switchProject(($event.target as HTMLSelectElement).value)"
          class="project-select"
        >
          <option v-for="p in auth.projects" :key="p.id" :value="p.id">
            {{ p.name }}{{ p.status === 'archived' ? ' [归档]' : '' }}
          </option>
        </select>
      </div>

      <!-- 导航 -->
      <nav class="nav">
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="`/${route.params.projectId}/${item.path}`"
          class="nav-item"
          :class="getNavClass(item.path)"
        >
          <svg class="nav-icon" viewBox="0 0 20 20" fill="currentColor">
            <!-- 知识库: open book -->
            <template v-if="item.icon === 'book'">
              <path d="M9 4.8L3.5 2.5C3.2 2.4 2.8 2.6 2.8 2.9v12.3c0 .3.2.5.4.6L9 17.2V4.8zM11 4.8v12.4l5.8-1.4c.2-.1.4-.3.4-.6V2.9c0-.3-.4-.5-.7-.4L11 4.8z"/>
            </template>
            <!-- 图谱: connected nodes -->
            <template v-else-if="item.icon === 'graph'">
              <circle cx="5" cy="5" r="2.5"/><circle cx="15" cy="5" r="2.5"/><circle cx="10" cy="15" r="2.5"/>
              <line x1="7" y1="7" x2="12.5" y2="13"/><line x1="12.5" y1="7" x2="7.5" y2="13"/>
            </template>
            <!-- 设置: gear -->
            <template v-else>
              <path d="M10 13a3 3 0 100-6 3 3 0 000 6z"/>
              <path d="M15.6 6.3l-.8-.3-.5-1.1.5-1.3c.1-.3-.1-.7-.4-.8l-.8-.4c-.3-.2-.6-.1-.8.2l-.7.9-1.1-.3-.3-1.2c-.1-.3-.4-.6-.7-.6h-.9c-.3 0-.6.3-.7.6l-.3 1.2-1.1.3-.7-.9c-.2-.3-.5-.4-.8-.2l-.8.4c-.3.1-.5.5-.4.8l.5 1.3-.5 1.1-.8.3c-.3.1-.5.5-.5.8l.2.9c.1.3.4.5.7.5l1.2.2.2 1.1-.9.8c-.2.2-.3.6-.1.9l.5.8c.2.3.5.4.8.3l1.2-.4 1 .6-.1 1.2c0 .3.3.6.6.7h.9c.3 0 .6-.3.7-.6l.1-1.2 1-.6 1.2.4c.3.1.6 0 .8-.3l.5-.8c.2-.3.1-.7-.1-.9l-.9-.8.2-1.1 1.2-.2c.3 0 .6-.3.7-.5l.2-.9c0-.3-.1-.7-.4-.8z"/>
            </template>
          </svg>
          {{ item.label }}
        </router-link>
      </nav>

      <!-- 底部用户区 -->
      <div class="sidebar-footer">
        <div class="user-avatar">{{ auth.user?.username?.[0]?.toUpperCase() || '?' }}</div>
        <div class="user-meta">
          <span class="user-name">{{ auth.user?.username }}</span>
          <span class="user-role">{{ auth.user?.role === 'admin' ? '管理员' : '用户' }}</span>
        </div>
        <button class="logout-btn" title="退出登录" @click="logout">
          <svg viewBox="0 0 20 20" fill="currentColor" width="16" height="16">
            <path d="M3 3a1 1 0 00-1 1v12a1 1 0 001 1h5v-2H4V5h4V3H3zM13 4l-1.4 1.4L14.2 8H7v2h7.2l-2.6 2.6L13 14l5-5-5-5z"/>
          </svg>
        </button>
      </div>
    </aside>

    <!-- 内容区 -->
    <main class="main">
      <header class="topbar" v-if="currentProject">
        <h1 class="project-title">{{ currentProject.name }}</h1>
        <span v-if="currentProject.status === 'archived'" class="badge badge-warning">已归档</span>
      </header>
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  min-height: 100vh;
  background: var(--bg-page);
}

/* ── 侧边栏 ── */
.sidebar {
  width: 250px;
  background: var(--sidebar-bg);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  height: 100vh;
  overflow-y: auto;
}

/* Logo */
.logo-section {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 18px 18px;
}

.logo-icon { width: 40px; height: 40px; flex-shrink: 0; }

.logo-title {
  display: block;
  font-size: 16px;
  font-weight: 700;
  color: #F1F5F9;
  letter-spacing: -0.3px;
  line-height: 1.2;
}

.logo-subtitle {
  display: block;
  font-size: 11px;
  color: var(--sidebar-muted);
  margin-top: 1px;
}

/* 项目切换 */
.project-area {
  padding: 0 14px 12px;
  border-bottom: 1px solid var(--sidebar-divider);
  margin-bottom: 4px;
}

.project-select {
  width: 100%;
  padding: 8px 10px;
  font-size: 13px;
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: var(--radius-sm);
  background: rgba(255,255,255,0.06);
  color: var(--sidebar-text);
  cursor: pointer;
  outline: none;
  transition: border-color var(--transition);
}
.project-select:hover { border-color: rgba(255,255,255,0.2); }
.project-select:focus { border-color: var(--accent); }

/* 导航 */
.nav {
  flex: 1;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: var(--radius-sm);
  color: var(--sidebar-muted);
  font-size: 14px;
  font-weight: 500;
  text-decoration: none;
  transition: all var(--transition);
  position: relative;
}

.nav-item:hover {
  background: var(--sidebar-hover-bg);
  color: var(--sidebar-text);
}

.nav-item.active {
  background: var(--sidebar-active-bg);
  color: var(--accent);
}

.nav-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  opacity: 0.7;
}
.nav-item.active .nav-icon { opacity: 1; }

/* 底部 */
.sidebar-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-top: 1px solid var(--sidebar-divider);
}

.user-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  flex-shrink: 0;
}

.user-meta { flex: 1; min-width: 0; }

.user-name {
  display: block;
  font-size: 13px;
  color: var(--sidebar-text);
  font-weight: 500;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-role {
  display: block;
  font-size: 11px;
  color: var(--sidebar-muted);
}

.logout-btn {
  background: none;
  color: var(--sidebar-muted);
  padding: 6px;
  border-radius: var(--radius-sm);
  transition: all var(--transition);
}
.logout-btn:hover {
  color: #F87171;
  background: rgba(248,113,113,0.1);
}

/* ── 主内容区 ── */
.main {
  flex: 1;
  min-width: 0;
}

.topbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 24px 40px 0;
}

.project-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.4px;
}
</style>
