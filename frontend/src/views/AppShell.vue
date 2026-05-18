<script setup lang="ts">
/**
 * 应用外壳——浅色侧边栏 + 自定义项目下拉 + SVG 导航。
 */
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { projectsApi } from '@/api/projects'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const dropdownOpen = ref(false)
const deleteTarget = ref<any>(null)
const deleting = ref(false)
const deleteError = ref('')

const activeProjects = computed(() => (auth.projects || []).filter((p: any) => p.status !== 'archived'))
const archivedProjects = computed(() => (auth.projects || []).filter((p: any) => p.status === 'archived'))
const currentProject = computed(() =>
  auth.projects.find((p: any) => p.id === route.params.projectId)
)

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

function switchProject(id: string) {
  dropdownOpen.value = false
  router.push(`/${id}`)
}

function toggleDropdown() { dropdownOpen.value = !dropdownOpen.value }
function closeDropdown() { dropdownOpen.value = false }
function goHome() { dropdownOpen.value = false; router.push({ path: '/', query: { new: '1' } }) }
function logout() { auth.logout(); router.push('/login') }

function confirmDelete(project: any) {
  deleteError.value = ''
  deleteTarget.value = project
}

async function executeDelete() {
  if (!deleteTarget.value) return
  deleting.value = true; deleteError.value = ''
  try {
    await projectsApi.delete(deleteTarget.value.id)
    await auth.initialize()
    // 如果删除的是当前项目，跳首页
    if (deleteTarget.value.id === route.params.projectId) {
      router.push('/')
    }
    deleteTarget.value = null
    dropdownOpen.value = false
  } catch (e: any) {
    deleteError.value = e.response?.data?.detail || '删除失败'
  } finally { deleting.value = false }
}
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
          <button class="project-trigger" @click="toggleDropdown">
            <span class="project-trigger-dot" />
            <span class="project-trigger-name">{{ currentProject?.name || '无项目' }}</span>
            <svg class="project-trigger-chevron" :class="{ open: dropdownOpen }" viewBox="0 0 20 20" fill="currentColor" width="14">
              <path d="M6 8l4 4 4-4" stroke="currentColor" stroke-width="2" fill="none"/>
            </svg>
          </button>

          <div v-if="dropdownOpen" class="project-dropdown">
            <div class="dropdown-header">切换项目</div>

            <div v-if="activeProjects.length === 0" class="dropdown-empty">暂无活跃项目</div>

            <div
              v-for="p in activeProjects" :key="p.id"
              class="dropdown-item"
              :class="{ current: p.id === route.params.projectId }"
            >
              <span class="dropdown-item-main" @click="switchProject(p.id)">
                <span class="dropdown-item-dot" />
                <span class="dropdown-item-name">{{ p.name }}</span>
                <span class="dropdown-item-role">{{ p.role === 'owner' ? 'Owner' : p.role === 'editor' ? 'Editor' : 'Viewer' }}</span>
              </span>
              <button
                v-if="p.role === 'owner'"
                class="dropdown-delete"
                title="删除项目"
                @click.stop="confirmDelete(p)"
              >
                <svg viewBox="0 0 16 16" fill="currentColor" width="13"><path d="M5 3h6v1H5zM6 5h4l-.4 8H6.4L6 5zM7 2h2v1H7z" fill-rule="evenodd"/></svg>
              </button>
            </div>

            <template v-if="archivedProjects.length > 0">
              <div class="dropdown-divider" />
              <div class="dropdown-section-title">已归档</div>
              <button
                v-for="p in archivedProjects" :key="p.id"
                class="dropdown-item archived"
                @click="switchProject(p.id)"
              >
                <span class="dropdown-item-dot archived-dot" />
                <span class="dropdown-item-name">{{ p.name }}</span>
              </button>
            </template>

            <div class="dropdown-divider" />
            <button class="dropdown-item new-project" @click="goHome">
              <svg viewBox="0 0 20 20" fill="currentColor" width="14"><path d="M10 4v12M4 10h12" stroke="currentColor" stroke-width="2" fill="none"/></svg>
              新建项目
            </button>
          </div>

          <!-- 点击外部关闭遮罩 -->
          <div v-if="dropdownOpen" class="dropdown-backdrop" @click="closeDropdown" />
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

    <!-- 删除确认弹窗 -->
    <div v-if="deleteTarget" class="modal-overlay" @click.self="deleteTarget = null">
      <div class="modal">
        <div class="modal-header">确认删除项目</div>
        <div class="modal-body">
          <p>确定要删除 <strong>{{ deleteTarget.name }}</strong> 吗？</p>
          <p style="color:var(--error-text);font-size:12px;margin-top:8px">此操作将删除项目下的所有 Wiki 页面、源文件和图谱数据，且不可撤销。</p>
          <div v-if="deleteError" class="error-tip">{{ deleteError }}</div>
        </div>
        <div class="modal-footer">
          <button class="btn-secondary" @click="deleteTarget = null" :disabled="deleting">取消</button>
          <button class="btn-danger" @click="executeDelete" :disabled="deleting">
            {{ deleting ? '删除中...' : '确认删除' }}
          </button>
        </div>
      </div>
    </div>

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

.project-switch { padding: 10px 12px; border-bottom: 1px solid var(--sidebar-divider); position: relative; }

.project-trigger {
  width: 100%; display: flex; align-items: center; gap: 9px;
  padding: 8px 10px; background: var(--bg-subtle); border: 1px solid transparent;
  border-radius: var(--radius); cursor: pointer; transition: all var(--transition);
}
.project-trigger:hover { background: var(--bg-card); border-color: var(--border); box-shadow: var(--shadow-xs); }

.project-trigger-dot {
  width: 7px; height: 7px; border-radius: 50%; background: var(--accent); flex-shrink: 0;
}
.project-trigger-name {
  flex: 1; text-align: left; font-size: 13px; font-weight: 600; color: var(--text-primary);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.project-trigger-chevron { color: var(--text-muted); flex-shrink: 0; transition: transform var(--transition); }
.project-trigger-chevron.open { transform: rotate(180deg); }

/* 下拉面板 */
.project-dropdown {
  position: absolute; left: 12px; right: 12px; top: calc(100% + 4px);
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius-lg); box-shadow: var(--shadow-lg);
  z-index: 100; overflow: hidden; animation: dropIn 0.15s ease;
}

.dropdown-header {
  padding: 10px 14px; font-size: 11px; font-weight: 600; color: var(--text-muted);
  text-transform: uppercase; letter-spacing: 0.5px;
  border-bottom: 1px solid var(--border-light);
}

.dropdown-empty { padding: 14px; font-size: 12px; color: var(--text-muted); text-align: center; }

.dropdown-item {
  width: 100%; display: flex; align-items: center; gap: 4px;
  padding: 4px 10px; background: transparent; border-radius: 0;
  transition: background var(--transition);
}
.dropdown-item:hover { background: var(--bg-subtle); }
.dropdown-item.current { background: var(--accent-light); }

.dropdown-item-main {
  flex: 1; display: flex; align-items: center; gap: 9px;
  padding: 5px 4px; background: transparent; border: none; border-radius: 0;
  font-size: 13px; color: var(--text-primary); text-align: left;
  cursor: pointer;
}
.dropdown-item.current .dropdown-item-name { color: var(--accent); font-weight: 600; }

.dropdown-item-dot {
  width: 7px; height: 7px; border-radius: 50%; background: var(--accent); flex-shrink: 0;
}
.dropdown-item.current .dropdown-item-dot { box-shadow: 0 0 0 3px var(--accent-ring); }

.dropdown-delete {
  padding: 5px; background: transparent; color: var(--text-muted);
  border-radius: var(--radius-sm); flex-shrink: 0;
  transition: all var(--transition);
}
.dropdown-delete:hover { color: #DC2626; background: var(--error-bg); }

.error-tip { background: var(--error-bg); color: var(--error-text); padding: 8px 12px; border-radius: var(--radius-sm); font-size: 12px; margin-top: 10px; }

.archived-dot { background: var(--text-muted); }

.dropdown-item-name { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dropdown-item-role { font-size: 11px; color: var(--text-muted); flex-shrink: 0; }

.dropdown-divider { height: 1px; background: var(--border-light); margin: 2px 0; }

.dropdown-section-title {
  padding: 6px 14px 4px; font-size: 10px; font-weight: 600; color: var(--text-muted);
  text-transform: uppercase; letter-spacing: 0.5px;
}

.dropdown-item.new-project {
  color: var(--accent); font-weight: 600; padding: 10px 14px;
}

.dropdown-backdrop { position: fixed; inset: 0; z-index: 99; }

@keyframes dropIn { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: translateY(0); } }

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

.main { flex: 1; min-width: 0; padding: 32px 40px 64px; }

.page-enter-active { animation: fadeIn 0.18s ease; }
.page-leave-active { animation: fadeIn 0.1s ease reverse; }

@keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
</style>
