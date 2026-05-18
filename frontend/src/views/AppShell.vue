<script setup lang="ts">
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const navItems = [
  { path: '', label: '知识库', icon: 'book' },
  { path: 'graph', label: '知识图谱', icon: 'graph' },
  { path: 'settings', label: '设置', icon: 'settings' },
]

function isActive(path: string): boolean {
  const pid = route.params.projectId as string
  const full = `/${pid}/${path}`.replace(/\/$/, '')
  const cur = route.path.replace(/\/$/, '')
  if (path === '') return cur === `/${pid}`
  return cur === full
}

function goHome() { router.push('/') }
function logout() { auth.logout(); router.push('/login') }
</script>

<template>
  <div class="shell">
    <!-- 浅色侧边栏 -->
    <aside class="sidebar">
      <div class="sidebar-top">
        <div class="brand" @click="goHome">
          <svg class="brand-logo" viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect width="36" height="36" rx="9" fill="url(#brand-grad)"/>
            <path d="M10.5 12.5h15v1.8H10.5zM10.5 17h10v1.8H10.5zM10.5 21.5h12v1.8H10.5z" fill="#fff"/>
            <circle cx="24.5" cy="13.4" r="1.5" fill="rgba(255,255,255,0.5)"/>
            <circle cx="27.5" cy="13.4" r="1.5" fill="rgba(255,255,255,0.5)"/>
            <circle cx="24.5" cy="17.9" r="1.5" fill="rgba(255,255,255,0.5)"/>
            <circle cx="27.5" cy="17.9" r="1.5" fill="rgba(255,255,255,0.5)"/>
            <circle cx="24.5" cy="22.4" r="1.5" fill="rgba(255,255,255,0.5)"/>
            <circle cx="27.5" cy="22.4" r="1.5" fill="rgba(255,255,255,0.5)"/>
            <defs>
              <linearGradient id="brand-grad" x1="0" y1="0" x2="36" y2="36">
                <stop stop-color="#D97706"/><stop offset="1" stop-color="#EA580C"/>
              </linearGradient>
            </defs>
          </svg>
          <div class="brand-text">
            <span class="brand-name">LLM Wiki</span>
            <span class="brand-desc">知识从不丢失</span>
          </div>
        </div>

        <!-- 项目切换 -->
        <div class="project-switch">
          <select
            :value="route.params.projectId"
            @change="router.push(`/${($event.target as HTMLSelectElement).value}`)"
          >
            <option v-for="p in auth.projects" :key="p.id" :value="p.id">
              {{ p.name }}{{ p.status === 'archived' ? ' [归档]' : '' }}
            </option>
          </select>
        </div>

        <!-- 导航 -->
        <nav class="nav">
          <router-link
            v-for="item in navItems" :key="item.path"
            :to="`/${route.params.projectId}/${item.path}`"
            class="nav-item" :class="{ active: isActive(item.path) }"
          >
            <svg class="nav-icon" viewBox="0 0 20 20" fill="currentColor">
              <template v-if="item.icon === 'book'">
                <path d="M9 4.8L3.5 2.5C3.2 2.4 2.8 2.6 2.8 2.9v12.3c0 .3.2.5.4.6L9 17.2V4.8zM11 4.8v12.4l5.8-1.4c.2-.1.4-.3.4-.6V2.9c0-.3-.4-.5-.7-.4L11 4.8z"/>
              </template>
              <template v-else-if="item.icon === 'graph'">
                <circle cx="4" cy="16" r="2.5"/><circle cx="10" cy="8" r="2.5"/><circle cx="16" cy="14" r="2.5"/>
                <line x1="6" y1="14.5" x2="8.5" y2="9.5" stroke="currentColor" stroke-width="1.5"/><line x1="11.5" y1="9.5" x2="14" y2="12.5" stroke="currentColor" stroke-width="1.5"/>
              </template>
              <template v-else>
                <path d="M10 13a3 3 0 100-6 3 3 0 000 6z" stroke="currentColor" stroke-width="1.5" fill="none"/>
                <path d="M15.4 6.4l-.7-.4-.5 1 .4 1.3c.1.3-.1.6-.4.7l-.8.4c-.2.1-.5.1-.7-.1l-.7-.9-1 .3-.3 1.1c-.1.3-.4.5-.7.5h-.9c-.3 0-.6-.2-.7-.5l-.3-1.1-1-.3-.7.9c-.2.2-.5.2-.7.1l-.8-.4c-.3-.1-.5-.4-.4-.7l.4-1.3-.5-1-.7.4c-.3.1-.5.4-.4.7l.2.9c.1.3.4.5.7.5l1.1.2.2 1.1-.9.7c-.2.2-.3.5-.1.8l.4.8c.2.2.5.3.7.2l1.2-.4.9.6-.1 1.1c0 .3.3.6.6.6h.9c.3 0 .6-.2.7-.5l.1-1.1.9-.6 1.2.4c.3.1.5 0 .7-.2l.4-.8c.2-.2.1-.6-.1-.8l-.9-.7.2-1.1 1.1-.2c.3 0 .6-.3.7-.5l.2-.9c0-.3-.1-.6-.4-.7z" fill="currentColor"/>
              </template>
            </svg>
            {{ item.label }}
          </router-link>
        </nav>
      </div>

      <!-- 底部 -->
      <div class="sidebar-footer">
        <div class="user-chip">
          <div class="user-avatar">{{ auth.user?.username?.[0]?.toUpperCase() || '?' }}</div>
          <div class="user-info">
            <span class="user-name">{{ auth.user?.username }}</span>
            <span class="user-role">{{ auth.user?.role === 'admin' ? '管理员' : '用户' }}</span>
          </div>
        </div>
        <button class="logout-icon" @click="logout" title="退出">
          <svg viewBox="0 0 20 20" fill="currentColor" width="16" height="16"><path d="M3 3a1 1 0 00-1 1v12a1 1 0 001 1h5v-2H4V5h4V3H3zM13 4l-1.4 1.4L14.2 8H7v2h7.2l-2.6 2.6L13 14l5-5-5-5z"/></svg>
        </button>
      </div>
    </aside>

    <main class="main">
      <router-view v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" :key="route.fullPath" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<style scoped>
.shell { display: flex; min-height: 100vh; background: var(--bg-page); }

.sidebar {
  width: 248px; background: var(--sidebar-bg); border-right: 1px solid var(--sidebar-divider);
  display: flex; flex-direction: column; flex-shrink: 0;
  position: sticky; top: 0; height: 100vh; overflow-y: auto;
}

.sidebar-top { flex: 1; }

.brand { display: flex; align-items: center; gap: 11px; padding: 18px 16px 14px; cursor: pointer; border-bottom: 1px solid var(--sidebar-divider); }
.brand-logo { width: 36px; height: 36px; flex-shrink: 0; }
.brand-name { display: block; font-size: 16px; font-weight: 700; color: var(--sidebar-text); letter-spacing: -0.3px; line-height: 1.15; }
.brand-desc { display: block; font-size: 11px; color: var(--sidebar-muted); }

.project-switch { padding: 12px 14px; border-bottom: 1px solid var(--sidebar-divider); }
.project-switch select { width: 100%; padding: 8px 10px; font-size: 13px; background: var(--bg-subtle); border-color: transparent; }
.project-switch select:focus { border-color: var(--accent); background: var(--bg-card); }

.nav { padding: 10px 8px; display: flex; flex-direction: column; gap: 1px; }

.nav-item {
  display: flex; align-items: center; gap: 10px; padding: 9px 12px;
  border-radius: var(--radius); color: var(--text-secondary); font-size: 14px;
  font-weight: 500; text-decoration: none; transition: all var(--transition);
}
.nav-item:hover { background: var(--sidebar-hover-bg); color: var(--text-primary); }
.nav-item.active { background: var(--sidebar-active-bg); color: var(--sidebar-accent); font-weight: 600; }

.nav-icon { width: 18px; height: 18px; flex-shrink: 0; opacity: 0.55; }
.nav-item.active .nav-icon { opacity: 1; }

.sidebar-footer {
  display: flex; align-items: center; padding: 12px 14px;
  border-top: 1px solid var(--sidebar-divider); gap: 8px;
}

.user-chip { display: flex; align-items: center; gap: 9px; flex: 1; min-width: 0; }
.user-avatar {
  width: 28px; height: 28px; border-radius: 50%; background: var(--accent);
  color: #fff; display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700; flex-shrink: 0;
}
.user-name { display: block; font-size: 12px; color: var(--text-primary); font-weight: 600; line-height: 1.15; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.user-role { display: block; font-size: 10.5px; color: var(--text-muted); }

.logout-icon {
  background: none; color: var(--text-muted); padding: 6px; border-radius: var(--radius-sm);
  transition: all var(--transition);
}
.logout-icon:hover { color: #DC2626; background: var(--error-bg); }

.main { flex: 1; min-width: 0; padding: 32px 40px 64px; max-width: 1120px; }

.page-enter-active { animation: fadeIn 0.18s ease; }
.page-leave-active { animation: fadeIn 0.1s ease reverse; }

@keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
</style>
