<script setup lang="ts">
/**
 * 应用外壳——侧边栏导航 + 项目切换器 + 内容区。
 */
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useProjectStore } from '@/stores/project'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const projectStore = useProjectStore()

// 导航项
const navItems = [
  { path: '', label: '知识库', icon: '📖' },
  { path: 'graph', label: '知识图谱', icon: '🔗' },
  { path: 'settings', label: '设置', icon: '⚙️' },
]

function switchProject(projectId: string) {
  projectStore.setCurrentProject(projectId)
  router.push(`/${projectId}`)
}

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-icon">🧠</span>
        <span class="brand-name">LLM Wiki</span>
      </div>

      <!-- 项目切换器 -->
      <div class="project-switcher">
        <select
          :value="route.params.projectId"
          @change="switchProject(($event.target as HTMLSelectElement).value)"
          class="project-select"
        >
          <option v-for="p in auth.projects" :key="p.id" :value="p.id">
            {{ p.name }} {{ p.status === 'archived' ? '📦' : '' }}
          </option>
        </select>
        <button class="new-project-btn" @click="router.push('/default')">+ 新建项目</button>
      </div>

      <!-- 导航 -->
      <nav class="nav">
        <router-link
          v-for="item in navItems" :key="item.path"
          :to="`/${route.params.projectId}/${item.path}`"
          class="nav-item"
          :class="{ active: route.path.endsWith(item.path) || (item.path === '' && route.path === `/${route.params.projectId}`) }"
        >
          {{ item.icon }} {{ item.label }}
        </router-link>
      </nav>

      <div class="sidebar-footer">
        <div class="user-info">
          <span>{{ auth.user?.username }}</span>
          <button class="logout-btn" @click="logout">退出</button>
        </div>
      </div>
    </aside>

    <main class="content">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  min-height: 100vh;
  background: var(--bg-page);
}

.sidebar {
  width: 240px;
  background: var(--bg-card);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  padding: 0;
  flex-shrink: 0;
}

.brand {
  padding: 20px 16px;
  text-align: center;
  border-bottom: 1px solid var(--border-color);
}

.brand-icon { font-size: 24px; }

.brand-name {
  display: block;
  font-weight: 700;
  font-size: 16px;
  color: var(--text-primary);
  margin-top: 4px;
}

.project-switcher { padding: 12px; border-bottom: 1px solid var(--border-color); }

.project-select {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-card);
  color: var(--text-primary);
  font-size: 13px;
  margin-bottom: 6px;
}

.new-project-btn {
  width: 100%;
  padding: 6px;
  background: transparent;
  color: var(--accent);
  border: 1px dashed var(--border-color);
  border-radius: var(--radius-sm);
  font-size: 12px;
}

.nav { flex: 1; padding: 8px; }

.nav-item {
  display: block;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-size: 14px;
  transition: background 0.15s;
  text-decoration: none;
}

.nav-item:hover { background: var(--bg-page); }

.nav-item.active {
  background: var(--bg-page);
  color: var(--accent);
  font-weight: 500;
}

.sidebar-footer {
  padding: 12px;
  border-top: 1px solid var(--border-color);
}

.user-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: var(--text-secondary);
}

.logout-btn {
  padding: 4px 8px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 11px;
}

.content {
  flex: 1;
  padding: 24px 32px;
  overflow-y: auto;
  max-width: 1200px;
}
</style>
